import os
import json
import time
import uuid
import datetime
import random
import requests
import pandas as pd
import streamlit as st

# Page Configuration - Google Flights Exact Dark Theme
st.set_page_config(
    page_title="Google Flights - Price Tracker",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =========================================================
# EXACT GOOGLE FLIGHTS DARK MODE CSS (PER SCREENSHOTS)
# =========================================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Google+Sans:wght@400;500;700&family=Roboto:wght@400;500;700&display=swap');

    html, body, [class*="css"], .stApp {
        background-color: #202124 !important;
        color: #e8eaed !important;
        font-family: 'Google Sans', 'Roboto', sans-serif !important;
    }

    /* TOP HEADER BAR */
    .gf-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 16px;
        background-color: #202124;
        border-bottom: 1px solid #3c4043;
        margin-bottom: 16px;
    }
    .gf-logo-group {
        display: flex;
        align-items: center;
        gap: 16px;
    }
    .gf-menu-icon {
        font-size: 20px;
        color: #bdc1c6;
        cursor: pointer;
    }
    .gf-google-logo {
        font-size: 22px;
        font-weight: 500;
        color: #ffffff;
        letter-spacing: -0.5px;
    }
    .gf-nav-chips {
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .gf-chip {
        background-color: transparent;
        color: #bdc1c6;
        padding: 6px 16px;
        border-radius: 18px;
        border: 1px solid #5f6368;
        font-size: 14px;
        font-weight: 500;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .gf-chip-active {
        background-color: #3c4043 !important;
        color: #8ab4f8 !important;
        border-color: #8ab4f8 !important;
    }

    /* HERO GRAPHIC BANNER */
    .hero-bg {
        width: 100%;
        height: 140px;
        background: linear-gradient(180deg, #171717 0%, #202124 100%);
        border-radius: 16px;
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        margin-bottom: 24px;
        overflow: hidden;
    }
    .hero-title-text {
        font-size: 40px;
        font-weight: 400;
        color: #ffffff;
        margin: 0;
        z-index: 2;
    }
    .hero-subtitle-text {
        font-size: 15px;
        color: #9aa0a6;
        margin-top: 4px;
    }

    /* SEARCH PANEL BOX */
    .search-panel {
        background-color: #303134;
        border-radius: 12px;
        padding: 20px 24px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
        margin-bottom: 24px;
        border: 1px solid #3c4043;
    }

    .stButton>button {
        background-color: #8ab4f8 !important;
        color: #202124 !important;
        font-weight: 600 !important;
        border-radius: 24px !important;
        padding: 8px 32px !important;
        border: none !important;
        font-size: 15px !important;
    }
    .stButton>button:hover {
        background-color: #aecbfa !important;
        box-shadow: 0 2px 8px rgba(138, 180, 248, 0.4) !important;
    }

    /* AI DEALS BANNER */
    .ai-banner {
        background-color: #303134;
        border-radius: 12px;
        padding: 18px 24px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
        border: 1px solid #3c4043;
    }
    .ai-banner-title {
        font-size: 16px;
        font-weight: 500;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .ai-banner-desc {
        font-size: 14px;
        color: #bdc1c6;
        margin-top: 4px;
    }

    /* DESTINATION CARDS & GRID */
    .deal-card {
        background-color: #303134;
        border: 1px solid #3c4043;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
    }
    .deal-title {
        font-size: 16px;
        font-weight: 500;
        color: #ffffff;
    }
    .deal-sub {
        font-size: 13px;
        color: #9aa0a6;
        margin-top: 4px;
    }
    .deal-price {
        font-size: 16px;
        font-weight: 500;
        color: #ffffff;
        text-align: right;
    }

    /* MAP CONTAINER PLACEHOLDER */
    .dark-map-box {
        background-color: #17191c;
        border-radius: 12px;
        height: 200px;
        border: 1px solid #3c4043;
        display: flex;
        align-items: center;
        justify-content: center;
        margin-bottom: 36px;
        position: relative;
    }
    .map-btn {
        background-color: #303134;
        color: #8ab4f8;
        padding: 10px 24px;
        border-radius: 20px;
        border: 1px solid #5f6368;
        font-weight: 500;
    }

    /* TICKET CARD ITEM */
    .ticket-price-green {
        color: #81c995;
        font-size: 18px;
        font-weight: 700;
    }

    /* FOOTER PILLS */
    .footer-pill {
        background-color: #303134;
        color: #bdc1c6;
        padding: 8px 18px;
        border-radius: 20px;
        border: 1px solid #5f6368;
        font-size: 13.5px;
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }

    #MainMenu, footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Local Storage Path
LOCAL_DATA_FILE = os.path.join(os.path.dirname(__file__), "active_trackers.json")
API_GATEWAY_URL = os.environ.get("API_GATEWAY_URL", "https://api.example.com/prod/track")

AIRPORTS = {
    "TRV": "Trivandrum (TRV)",
    "BLR": "Bengaluru (BLR)",
    "CJB": "Coimbatore (CJB)",
    "MAA": "Chennai (MAA)",
    "DEL": "New Delhi (DEL)",
    "BOM": "Mumbai (BOM)",
    "HYD": "Hyderabad (HYD)",
    "COK": "Cochin (COK)"
}

# =========================================================
# HELPER & INTEGRATION FUNCTIONS
# =========================================================
def load_trackers():
    """Load tracked routes from local JSON storage."""
    if os.path.exists(LOCAL_DATA_FILE):
        try:
            with open(LOCAL_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_local_tracker(payload):
    """Save tracked route payload locally (fallback testing)."""
    trackers = load_trackers()
    # Ensure current timestamp details are populated
    tracker_item = {
        "RouteId": payload.get("RouteId", f"TRK-{uuid.uuid4().hex[:8]}"),
        "UserId": payload.get("UserId", payload.get("email")),
        "email": payload.get("email", payload.get("UserId")),
        "origin": payload.get("origin", payload.get("Origin")),
        "Origin": payload.get("Origin", payload.get("origin")),
        "destination": payload.get("destination", payload.get("Destination")),
        "Destination": payload.get("Destination", payload.get("destination")),
        "departure_date": payload.get("departure_date", payload.get("DepartureDate")),
        "DepartureDate": payload.get("DepartureDate", payload.get("departure_date")),
        "target_price": float(payload.get("target_price", payload.get("TargetPrice", 0))),
        "TargetPrice": float(payload.get("TargetPrice", payload.get("target_price", 0))),
        "current_price": round(float(payload.get("target_price", payload.get("TargetPrice", 0))) * 0.96, 2),
        "status": "Monitoring Active",
        "CreatedAt": payload.get("CreatedAt", datetime.datetime.utcnow().isoformat() + "Z"),
        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    # Prepend to list
    trackers = [t for t in trackers if t.get("RouteId") != tracker_item["RouteId"]]
    trackers.insert(0, tracker_item)
    with open(LOCAL_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(trackers, f, indent=2)
    return tracker_item

def delete_tracker(route_id):
    """Delete tracker by RouteId from local storage."""
    trackers = load_trackers()
    updated = [t for t in trackers if t.get("RouteId") != route_id and t.get("tracker_id") != route_id]
    with open(LOCAL_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)

def send_tracked_route_payload(payload):
    """
    API Gateway Integration Layer:
    Attempts HTTP POST to AWS API Gateway endpoint.
    Falls back to local handler if offline or endpoint is placeholder/unreachable.
    """
    headers = {"Content-Type": "application/json"}
    
    # Check if a valid remote URL is provided
    if API_GATEWAY_URL and not API_GATEWAY_URL.startswith("https://api.example.com"):
        try:
            response = requests.post(API_GATEWAY_URL, json=payload, headers=headers, timeout=5)
            if response.status_code in [200, 201]:
                save_local_tracker(payload)
                return True, f"Successfully registered tracker via AWS API Gateway! (HTTP {response.status_code})"
            else:
                # Save locally on non-200 API response
                save_local_tracker(payload)
                return False, f"API Gateway returned status {response.status_code}. Saved locally to active_trackers.json as fallback."
        except Exception as e:
            save_local_tracker(payload)
            return False, f"Could not connect to API Gateway ({str(e)}). Saved locally to active_trackers.json (Offline mode)."
    else:
        # Save locally in offline / dev mode
        save_local_tracker(payload)
        return True, "Saved route tracker locally in active_trackers.json (Offline / Local Fallback Mode)."

# =========================================================
# TOP NAVIGATION HEADER
# =========================================================
st.markdown("""
<div class="gf-header">
    <div class="gf-logo-group">
        <span class="gf-menu-icon">☰</span>
        <span class="gf-google-logo">Google</span>
    </div>
    <div class="gf-nav-chips">
        <span class="gf-chip">🧭 Explore</span>
        <span class="gf-chip gf-chip-active">✈️ Flights</span>
        <span class="gf-chip">🛏️ Hotels</span>
        <span class="gf-chip">🏠 Vacation rentals</span>
    </div>
    <div>
        <span style="font-size:18px; color:#bdc1c6; cursor:pointer;">☀️ ⚙️ 👤</span>
    </div>
</div>
""", unsafe_allow_html=True)

# =========================================================
# HERO BANNER
# =========================================================
st.markdown("""
<div class="hero-bg">
    <div class="hero-title-text">Flights</div>
    <div class="hero-subtitle-text">Serverless Price Monitoring System</div>
</div>
""", unsafe_allow_html=True)

# =========================================================
# MAIN DASHBOARD TABS
# =========================================================
tab_track, tab_dashboard = st.tabs(["✈️ Track Flight Route", "📊 Active Trackers Dashboard"])

# ---------------------------------------------------------
# TAB 1: TRACK FLIGHT ROUTE FORM
# ---------------------------------------------------------
with tab_track:
    st.markdown("### 🔔 Create New Flight Price Tracker")
    st.caption("Configure price tracking matching our AWS DynamoDB `TrackedRoutes` schema.")

    with st.form(key="track_route_form"):
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            user_email = st.text_input(
                "User Email",
                value="adwaitharun2005@gmail.com",
                help="Email address for price drop notifications."
            )
            origin_code = st.selectbox(
                "Origin Airport Code",
                options=list(AIRPORTS.keys()),
                index=0,
                format_func=lambda x: f"{x} - {AIRPORTS[x]}"
            )
            dep_date = st.date_input(
                "Departure Date",
                value=datetime.date.today() + datetime.timedelta(days=14),
                min_value=datetime.date.today()
            )
        
        with col_f2:
            dest_code = st.selectbox(
                "Destination Airport Code",
                options=list(AIRPORTS.keys()),
                index=1,
                format_func=lambda x: f"{x} - {AIRPORTS[x]}"
            )
            target_price = st.number_input(
                "Target Price (INR ₹)",
                min_value=500.0,
                max_value=200000.0,
                value=5000.0,
                step=250.0,
                help="Receive notifications when flight prices drop below this threshold."
            )
            st.markdown("<br>", unsafe_allow_html=True)
            submit_btn = st.form_submit_button("🚀 Start Tracking", use_container_width=True)

    if submit_btn:
        if not user_email or "@" not in user_email:
            st.error("Please enter a valid email address.")
        elif origin_code == dest_code:
            st.error("Origin and Destination airports must be different.")
        else:
            route_id = f"TRK-{uuid.uuid4().hex[:8].upper()}"
            created_at_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            # DynamoDB TrackedRoutes Table Schema Payload
            payload = {
                "RouteId": route_id,
                "UserId": user_email,
                "email": user_email,
                "origin": origin_code,
                "Origin": origin_code,
                "destination": dest_code,
                "Destination": dest_code,
                "departure_date": str(dep_date),
                "DepartureDate": str(dep_date),
                "target_price": float(target_price),
                "TargetPrice": float(target_price),
                "CreatedAt": created_at_iso
            }

            st.markdown("#### 📦 Generated Payload (DynamoDB `TrackedRoutes` Schema)")
            st.json(payload)

            with st.spinner("Sending payload to AWS API Gateway..."):
                success, msg = send_tracked_route_payload(payload)

            if success:
                st.success(f"✅ {msg}")
            else:
                st.warning(f"⚠️ {msg}")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # ---------------------------------------------------------
    # FLIGHT RESULTS SECTION (BEST DEPARTING FLIGHTS)
    # ---------------------------------------------------------
    st.markdown("### Best departing flights")
    st.caption("Ranked based on price, speed, and convenience")

    airlines_data = [
        {"name": "IndiGo", "code": "6E", "dep": "06:00", "arr": "08:15", "dur": "2 hr 15 min", "price": 4850},
        {"name": "Air India", "code": "AI", "dep": "09:30", "arr": "11:55", "dur": "2 hr 25 min", "price": 5200},
        {"name": "Akasa Air", "code": "QP", "dep": "14:10", "arr": "16:30", "dur": "2 hr 20 min", "price": 4490},
        {"name": "Vistara", "code": "UK", "dep": "18:45", "arr": "21:10", "dur": "2 hr 25 min", "price": 5800}
    ]

    for idx, fl in enumerate(airlines_data):
        col_c1, col_c2, col_c3, col_c4, col_c5 = st.columns([3, 3, 2, 2, 2])
        with col_c1:
            st.markdown(f"**✈️ {fl['name']}**")
            st.caption(f"`{fl['code']}-10{idx+1}` • Nonstop")
        with col_c2:
            st.markdown(f"**{fl['dep']} – {fl['arr']}**")
            st.caption(f"{origin_code}–{dest_code}")
        with col_c3:
            st.markdown(f"{fl['dur']}")
            st.caption("🌱 -16% emissions")
        with col_c4:
            st.markdown(f"<span class='ticket-price-green'>₹{fl['price']:,}</span>", unsafe_allow_html=True)
            st.caption("one way")
        with col_c5:
            if st.button("Quick Track", key=f"quick_track_{idx}"):
                q_payload = {
                    "RouteId": f"TRK-{uuid.uuid4().hex[:8].upper()}",
                    "UserId": user_email if 'user_email' in locals() and user_email else "adwaitharun2005@gmail.com",
                    "email": user_email if 'user_email' in locals() and user_email else "adwaitharun2005@gmail.com",
                    "origin": origin_code,
                    "Origin": origin_code,
                    "destination": dest_code,
                    "Destination": dest_code,
                    "departure_date": str(dep_date),
                    "DepartureDate": str(dep_date),
                    "target_price": float(fl['price']),
                    "TargetPrice": float(fl['price']),
                    "CreatedAt": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                send_tracked_route_payload(q_payload)
                st.toast(f"✅ Added tracker for {fl['name']} (₹{fl['price']})!")

        st.markdown("<hr style='border-color:#3c4043; margin:8px 0;'>", unsafe_allow_html=True)


# ---------------------------------------------------------
# TAB 2: ACTIVE TRACKERS DASHBOARD
# ---------------------------------------------------------
with tab_dashboard:
    st.markdown("### 📊 Active Tracked Routes Dashboard")
    st.caption("Mock view of routes currently being monitored by our background processor.")

    trackers = load_trackers()

    if not trackers:
        st.info("No active flight trackers found. Use the 'Track Flight Route' form to add one.")
    else:
        st.markdown(f"Total Active Trackers: **{len(trackers)}**")
        
        # Display as cards or summary table
        for t in trackers:
            r_id = t.get("RouteId", t.get("tracker_id", "N/A"))
            email = t.get("email", t.get("UserId", "N/A"))
            orig = t.get("origin", t.get("Origin", "N/A"))
            dest = t.get("destination", t.get("Destination", "N/A"))
            date_val = t.get("departure_date", t.get("DepartureDate", "N/A"))
            target = t.get("target_price", t.get("TargetPrice", 0))
            curr = t.get("current_price", round(float(target) * 0.95, 2))
            created = t.get("CreatedAt", t.get("created_at", "N/A"))

            with st.container():
                d_col1, d_col2, d_col3, d_col4, d_col5 = st.columns([2.5, 2.5, 2.5, 2.5, 1.5])
                
                with d_col1:
                    st.markdown(f"**✈️ {orig} ➔ {dest}**")
                    st.caption(f"ID: `{r_id}`")
                
                with d_col2:
                    st.markdown(f"👤 **{email}**")
                    st.caption(f"Departure: {date_val}")
                
                with d_col3:
                    st.markdown(f"🎯 Target: **₹{float(target):,.2f}**")
                    st.markdown(f"💵 Current: **₹{float(curr):,.2f}**")
                
                with d_col4:
                    if float(curr) <= float(target):
                        st.markdown("🟢 <span style='color:#81c995; font-weight:bold;'>Target Price Met</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("🟡 <span style='color:#fdd835; font-weight:bold;'>Monitoring...</span>", unsafe_allow_html=True)
                    st.caption(f"Created: {created[:10] if isinstance(created, str) else created}")

                with d_col5:
                    if st.button("🗑️ Delete", key=f"del_{r_id}"):
                        delete_tracker(r_id)
                        st.toast(f"Removed tracker {r_id}")
                        st.rerun()

                st.markdown("<hr style='border-color:#3c4043; margin:8px 0;'>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 Refresh Dashboard", use_container_width=False):
            st.rerun()

st.markdown("<br><hr style='border-color:#3c4043;'><br>", unsafe_allow_html=True)

# =========================================================
# USEFUL TOOLS & FOOTER
# =========================================================
st.markdown("### Useful tools to help you find the best airline tickets")
t_col1, t_col2 = st.columns([5, 7])

with t_col1:
    st.markdown("""
    <div class="deal-card">
        <div class="deal-title">📅 Find the cheapest days to fly</div>
        <div class="deal-sub">Date grid and price graph offer quick price comparisons</div>
    </div>
    <div class="deal-card">
        <div class="deal-title">🔔 Track flight prices for a trip</div>
        <div class="deal-sub">Observe price changes and receive instant email notifications</div>
    </div>
    """, unsafe_allow_html=True)

with t_col2:
    st.markdown("""
    <div class="deal-card" style="padding: 24px;">
        <h4 style="color:#ffffff; margin-bottom:8px;">DynamoDB & Serverless Architecture Integration</h4>
        <p style="color:#bdc1c6; font-size:13.5px; line-height:1.5;">
            Tracked routes are formatted as JSON payloads sent directly to our AWS API Gateway endpoint.
            Our background Lambda API Fetcher continuously scrapes flight prices and checks against your target price threshold.
        </p>
    </div>
    """, unsafe_allow_html=True)

# Footer pills
st.markdown("""
<div style="display:flex; justify-content:center; gap:16px; margin-top:24px; margin-bottom:24px;">
    <span class="footer-pill">🌐 Language · English</span>
    <span class="footer-pill">📍 Location · India</span>
    <span class="footer-pill">💰 Currency · INR</span>
</div>
""", unsafe_allow_html=True)
