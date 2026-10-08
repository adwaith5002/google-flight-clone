import sys
import os
import json
import uuid
import datetime
import requests
import pandas as pd
import streamlit as st
import boto3
from botocore.exceptions import ClientError

# Add parent directory to system path for importing fetcher & alert_engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

try:
    from src.api_fetcher.fetcher import fetch_flight_prices, write_price_history
    from src.processor.alert_engine import evaluate_route_price_alerts, send_sns_price_alert, get_latest_price_history
except ImportError:
    pass

# Page Configuration
st.set_page_config(
    page_title="Google Flights - Serverless Price Monitor",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Dark Mode Google Flights Theme)
st.markdown("""
<style>
    .main { background-color: #202124; color: #e8eaed; }
    .stButton>button {
        background-color: #8ab4f8; color: #202124; font-weight: 600;
        border-radius: 24px; padding: 0.5rem 1.5rem; border: none; transition: all 0.2s ease;
    }
    .stButton>button:hover { background-color: #aecbfa; box-shadow: 0 1px 3px rgba(0,0,0,0.3); }
    .card {
        background-color: #2d2e31; border-radius: 12px; padding: 1.5rem;
        margin-bottom: 1rem; border: 1px solid #3c4043;
    }
    .metric-value { font-size: 1.8rem; font-weight: 700; color: #8ab4f8; }
    .badge-green { background-color: #137333; color: #e6f4ea; padding: 4px 12px; border-radius: 16px; font-weight: 600; font-size: 0.85rem; }
    .badge-yellow { background-color: #b06000; color: #fef7e0; padding: 4px 12px; border-radius: 16px; font-weight: 600; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)

# AWS Configuration & Local Fallback
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TRACKED_ROUTES_TABLE = os.environ.get("TRACKED_ROUTES_TABLE", "TrackedRoutes")
DEFAULT_SNS_ARN = "arn:aws:sns:us-east-1:309272175061:FlightPriceAlertsTopic"
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", DEFAULT_SNS_ARN)
LOCAL_STORAGE_FILE = os.path.join(os.path.dirname(__file__), "active_trackers.json")

AIRPORTS = {
    "TRV": "Trivandrum (TRV)",
    "BLR": "Bengaluru (BLR)",
    "DEL": "New Delhi (DEL)",
    "BOM": "Mumbai (BOM)",
    "MAA": "Chennai (MAA)",
    "CJB": "Coimbatore (CJB)",
    "HYD": "Hyderabad (HYD)",
    "CCU": "Kolkata (CCU)"
}


def load_aws_trackers():
    """Fetches active trackers directly from live AWS DynamoDB (with local fallback)."""
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(TRACKED_ROUTES_TABLE)
        res = table.scan()
        items = res.get("Items", [])
        if items:
            return items
    except Exception:
        pass
    
    # Local fallback file if AWS DynamoDB connection is offline
    if os.path.exists(LOCAL_STORAGE_FILE):
        try:
            with open(LOCAL_STORAGE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_tracker_to_aws(payload):
    """Saves route payload directly to live AWS DynamoDB TrackedRoutes table."""
    try:
        dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
        table = dynamodb.Table(TRACKED_ROUTES_TABLE)
        
        # Format payload for DynamoDB
        db_item = {
            "RouteId": str(payload["RouteId"]),
            "UserId": str(payload["UserId"]),
            "email": str(payload["UserId"]),
            "Origin": str(payload["Origin"]),
            "Destination": str(payload["Destination"]),
            "DepartureDate": str(payload["DepartureDate"]),
            "TargetPrice": float(payload["TargetPrice"]),
            "CreatedAt": str(payload["CreatedAt"])
        }
        table.put_item(Item=db_item)
        return True, "Saved to AWS DynamoDB"
    except Exception as e:
        # Save to local file fallback
        trackers = load_aws_trackers()
        trackers.append(payload)
        with open(LOCAL_STORAGE_FILE, "w") as f:
            json.dump(trackers, f, indent=2)
        return False, f"Saved locally ({e})"


# Sidebar Info
st.sidebar.image("https://www.gstatic.com/images/branding/product/2x/google_flights_64dp.png", width=50)
st.sidebar.title("Flight Price Monitor")
st.sidebar.markdown("Serverless Cloud System")
st.sidebar.markdown("---")
st.sidebar.info(f"**AWS Region:** `{AWS_REGION}`\n\n**DynamoDB Table:** `{TRACKED_ROUTES_TABLE}`\n\n**SNS Topic:**\n`{SNS_TOPIC_ARN.split(':')[-1]}`")

st.title("✈️ Google Flights - Serverless Price Monitor")
st.caption("Event-Driven Flight Fares Ingestion & Automated SNS Price Drop Alerts")

tab1, tab2, tab3 = st.tabs(["✈️ Track New Route", "📊 Active Trackers Dashboard", "⚙️ Cloud Web Controls"])

# TAB 1: Route Tracker Form
with tab1:
    st.subheader("Configure Flight Price Tracker")
    st.markdown("Set up a serverless price alert. You'll receive an email notification when airfares drop below your target price.")
    
    with st.form("tracker_form"):
        col1, col2 = st.columns(2)
        with col1:
            user_email = st.text_input("User Email Address", value="adwaitharun2005@gmail.com", help="Email for SNS alerts")
            origin_code = st.selectbox("Origin Airport", list(AIRPORTS.keys()), index=0, format_func=lambda x: AIRPORTS[x])
            departure_date = st.date_input("Departure Date", value=datetime.date.today() + datetime.timedelta(days=14))
        
        with col2:
            target_price = st.number_input("Target Price (₹ INR)", min_value=500, max_value=50000, value=5000, step=500)
            dest_code = st.selectbox("Destination Airport", list(AIRPORTS.keys()), index=1, format_func=lambda x: AIRPORTS[x])
        
        submit_btn = st.form_submit_button("🚀 Start Tracking Route", use_container_width=True)

    if submit_btn:
        if origin_code == dest_code:
            st.error("⚠️ Origin and Destination airports cannot be identical!")
        else:
            route_id = f"TRK-{uuid.uuid4().hex[:8].upper()}"
            payload = {
                "RouteId": route_id,
                "UserId": user_email,
                "Origin": origin_code,
                "Destination": dest_code,
                "DepartureDate": str(departure_date),
                "TargetPrice": float(target_price),
                "CreatedAt": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            
            success, msg = save_tracker_to_aws(payload)
            st.success(f"✅ Route Tracker Created Successfully! ({msg})")
            st.json(payload)
            st.toast(f"Tracking {origin_code} ➔ {dest_code} at ₹{target_price:,}", icon="✈️")

# TAB 2: Dashboard
with tab2:
    st.subheader("Active Route Trackers & Live Fares")
    trackers = load_aws_trackers()
    
    if not trackers:
        st.warning("No active route trackers found. Create one in the first tab!")
    else:
        st.write(f"Total Active Trackers: **{len(trackers)}**")
        
        for tracker in trackers:
            route_id = tracker.get("RouteId", "N/A")
            origin = tracker.get("Origin", "N/A")
            dest = tracker.get("Destination", "N/A")
            target = float(tracker.get("TargetPrice", 0))
            email = tracker.get("UserId", tracker.get("email", "N/A"))
            dep_date = tracker.get("DepartureDate", "N/A")
            
            # Get latest price entry
            latest_info = get_latest_price_history(route_id)
            curr_price = latest_info.get("Price", 0)
            airline = latest_info.get("Airline", "Airline")
            
            with st.container():
                st.markdown(f"""
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h3>✈️ {origin} ➔ {dest}</h3>
                        <span class="{'badge-green' if curr_price <= target else 'badge-yellow'}">
                            {'🎯 Target Met (₹' + str(curr_price) + ')' if curr_price <= target else '👀 Monitoring (₹' + str(curr_price) + ')'}
                        </span>
                    </div>
                    <p><b>Target Price:</b> ₹{target:,.2f} | <b>Current Price:</b> ₹{curr_price:,.2f} ({airline})</p>
                    <p><b>Departure Date:</b> {dep_date} | <b>Recipient Email:</b> {email} | <b>Route ID:</b> <code>{route_id}</code></p>
                </div>
                """, unsafe_allow_html=True)

# TAB 3: Web Controls for Cloud Tasks
with tab3:
    st.subheader("⚡ Cloud Automation & Web Execution")
    st.markdown("Trigger backend AWS serverless tasks directly from your web browser without terminal commands.")
    
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("### 1. Flight Price Ingestion")
        st.caption("Fetch live/mock flight prices and write to AWS DynamoDB `PriceHistory` table.")
        if st.button("🔄 Fetch & Ingest Latest Fares Now", use_container_width=True):
            with st.spinner("Fetching prices and writing to AWS DynamoDB..."):
                try:
                    os.environ["AWS_REGION"] = AWS_REGION
                    os.environ["TRACKED_ROUTES_TABLE"] = TRACKED_ROUTES_TABLE
                    
                    from src.api_fetcher.fetcher import lambda_handler
                    res = lambda_handler({}, None)
                    st.success("✅ Flight Price Ingestion Completed!")
                    st.json(json.loads(res["body"]))
                except Exception as e:
                    st.error(f"Ingestion failed: {e}")

    with col_b:
        st.markdown("### 2. Event-Driven Alert Processor")
        st.caption("Evaluate routes vs target thresholds and send live **Amazon SNS Email Alerts**.")
        if st.button("📩 Evaluate & Send SNS Email Alert", use_container_width=True):
            with st.spinner("Evaluating price thresholds & publishing SNS email..."):
                try:
                    os.environ["AWS_REGION"] = AWS_REGION
                    os.environ["SNS_TOPIC_ARN"] = SNS_TOPIC_ARN
                    
                    from src.processor.alert_engine import lambda_handler as alert_handler
                    res = alert_handler({}, None)
                    body_json = json.loads(res["body"])
                    
                    st.success(f"✅ Alert Engine Executed! ({body_json.get('alerts_triggered_count', 0)} email alert(s) sent)")
                    st.json(body_json)
                    st.balloons()
                except Exception as e:
                    st.error(f"Alert engine failed: {e}")

st.markdown("---")
st.caption("Cloud Flight Price Monitoring System • Built on AWS Serverless Architecture (DynamoDB, Lambda, SNS, EventBridge)")
