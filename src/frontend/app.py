"""
Google Flights – Serverless Price Monitor
End-to-end Streamlit app:
  Tab 1 – Search flights & set a price-drop tracker (with Advanced Filters & Sorting)
  Tab 2 – My active trackers (with Analytics, Multi-Currency, Lifecycle Controls & CSV Export)
  Tab 3 – Mock Data Injector (seed PriceHistory and fire SNS alerts)
"""

import sys, os, json, uuid, datetime, random, decimal, logging
import pandas as pd
import streamlit as st
import boto3
from botocore.exceptions import ClientError
from src.database.local_store import (
    load_items, save_items, update_tracker_status,
    update_tracker_target_price, delete_tracker
)
from src.utils.currency import (
    convert_currency, format_currency, get_supported_currencies, get_currency_symbol
)
from src.processor.analytics import (
    calculate_route_analytics, export_trackers_to_csv, export_price_history_to_csv
)
import src.frontend.auth as auth

# ── path so we can import fetcher / alert_engine ──────────────────────────────
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
try:
    from src.api_fetcher.fetcher import write_price_history, AIRLINES
    from src.processor.alert_engine import send_sns_price_alert, get_latest_price_history
except ImportError:
    AIRLINES = [
        {"name": "IndiGo",   "code": "6E"},
        {"name": "Air India","code": "AI"},
        {"name": "Akasa Air","code": "QP"},
        {"name": "Vistara",  "code": "UK"},
        {"name": "SpiceJet", "code": "SG"},
    ]
    def write_price_history(route_id, price, airline, **kw):
        return False, "Price-history writer could not be imported"
    def send_sns_price_alert(email, route_info, price_info):
        return False, "SNS sender could not be imported"
    def get_latest_price_history(route_id):
        return {"Price": 0.0, "Airline": "N/A", "Timestamp": ""}

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Google Flights – Price Monitor",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  html, body, [data-testid="stAppViewContainer"] { background:#202124; color:#e8eaed; }
  [data-testid="stSidebar"] { background:#292a2d; }
  h1,h2,h3,h4 { color:#e8eaed; }
  .stButton>button {
    background:#8ab4f8; color:#202124; font-weight:700;
    border-radius:24px; padding:.45rem 1.4rem; border:none; transition:.15s;
  }
  .stButton>button:hover { background:#aecbfa; }
  .flight-card {
    background:#2d2e31; border:1px solid #3c4043; border-radius:12px;
    padding:1rem 1.25rem; margin-bottom:.75rem;
    display:flex; justify-content:space-between; align-items:center;
  }
  .tracker-card {
    background:#292a2d; border:1px solid #3c4043; border-radius:12px;
    padding:1.25rem; margin-bottom:1rem;
  }
  .badge-green { background:#137333; color:#e6f4ea; padding:3px 10px; border-radius:12px; font-size:.8rem; font-weight:700; }
  .badge-yellow{ background:#b06000; color:#fef7e0; padding:3px 10px; border-radius:12px; font-size:.8rem; font-weight:700; }
  .badge-gray  { background:#5f6368; color:#f1f3f4; padding:3px 10px; border-radius:12px; font-size:.8rem; font-weight:700; }
  .badge-blue  { background:#1a73e8; color:#e8f0fe; padding:3px 10px; border-radius:12px; font-size:.8rem; font-weight:700; }
  .price-big { font-size:1.6rem; font-weight:800; color:#8ab4f8; }
  .airline-label { font-size:.9rem; color:#9aa0a6; }
  hr { border-color:#3c4043; }
</style>
""", unsafe_allow_html=True)

# ── constants ─────────────────────────────────────────────────────────────────
AWS_REGION           = os.environ.get("AWS_REGION",           "us-east-1")
TRACKED_ROUTES_TABLE = os.environ.get("TRACKED_ROUTES_TABLE", "TrackedRoutes")
PRICE_HISTORY_TABLE  = os.environ.get("PRICE_HISTORY_TABLE",  "PriceHistory")
SNS_TOPIC_ARN        = os.environ.get("SNS_TOPIC_ARN",        "")
LOCAL_FILE           = os.path.join(os.path.dirname(__file__), "active_trackers.json")
logger               = logging.getLogger(__name__)

AIRPORTS = {
    "TRV":"Trivandrum",   "BLR":"Bengaluru",  "DEL":"New Delhi",
    "BOM":"Mumbai",       "MAA":"Chennai",    "CJB":"Coimbatore",
    "HYD":"Hyderabad",    "CCU":"Kolkata",
}

# base fare matrix (INR)
BASE_FARES = {
    ("TRV","BLR"):3200, ("BLR","TRV"):3400, ("TRV","DEL"):7200, ("DEL","TRV"):7500,
    ("TRV","BOM"):5800, ("BOM","TRV"):6000, ("TRV","MAA"):2600, ("MAA","TRV"):2700,
    ("CJB","MAA"):2800, ("MAA","CJB"):2900, ("BLR","DEL"):5500, ("DEL","BLR"):5700,
    ("BOM","DEL"):4800, ("DEL","BOM"):5000, ("HYD","BLR"):3500, ("BLR","HYD"):3600,
}

# ── helpers ───────────────────────────────────────────────────────────────────
def to_float(x):
    if isinstance(x, decimal.Decimal): return float(x)
    if isinstance(x, list):  return [to_float(i) for i in x]
    if isinstance(x, dict):  return {k: to_float(v) for k,v in x.items()}
    return x

def dynamodb_table(name):
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(name)

def load_db_trackers():
    trackers_by_id = {
        item["RouteId"]: to_float(item)
        for item in load_items("trackers")
        if item.get("RouteId")
    }
    try:
        table = dynamodb_table(TRACKED_ROUTES_TABLE)
        res = table.scan()
        for item in res.get("Items", []):
            trackers_by_id[item["RouteId"]] = to_float(item)
        while res.get("LastEvaluatedKey"):
            res = table.scan(ExclusiveStartKey=res["LastEvaluatedKey"])
            for item in res.get("Items", []):
                trackers_by_id[item["RouteId"]] = to_float(item)
    except Exception as error:
        logger.warning("Could not load all trackers from DynamoDB: %s", error)

    try:
        with open(LOCAL_FILE, encoding="utf-8") as local_file:
            local_trackers = json.load(local_file)
        for item in local_trackers:
            if item.get("RouteId"):
                trackers_by_id.setdefault(item["RouteId"], to_float(item))
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Could not load local trackers: %s", error)
    return list(trackers_by_id.values())

def save_tracker_db(t):
    item = {
        "RouteId":      t["RouteId"],
        "UserId":       t["UserId"],
        "email":        t["UserId"],
        "Origin":       t["Origin"],
        "Destination":  t["Destination"],
        "DepartureDate":t["DepartureDate"],
        "TargetPrice":  float(t["TargetPrice"]),
        "Status":       t.get("Status", "Active"),
        "CreatedAt":    t["CreatedAt"],
    }
    try:
        dynamodb_table(TRACKED_ROUTES_TABLE).put_item(Item=item)
        database_saved = True
    except Exception as error:
        logger.warning("Could not save tracker to DynamoDB: %s", error)
        database_saved = False

    existing = load_db_trackers()
    by_id = {tracker.get("RouteId"): tracker for tracker in existing}
    by_id[item["RouteId"]] = item
    save_items("trackers", list(by_id.values()))
    with open(LOCAL_FILE, "w", encoding="utf-8") as local_file:
        json.dump(list(by_id.values()), local_file, indent=2)
    return database_saved

def mock_flights(origin, dest, date_str):
    """Generate realistic mock flight options for a route."""
    base = BASE_FARES.get((origin, dest), 5000)
    random.seed(f"{origin}{dest}{date_str}")
    results = []
    deps = ["06:10","08:45","11:30","14:15","17:50","20:05"]
    for i, al in enumerate(AIRLINES):
        var   = random.uniform(0.82, 1.22)
        price = round(base * var / 50) * 50
        dep   = deps[i % len(deps)]
        hr,mn = map(int, dep.split(":"))
        dur_m = random.randint(65, 145)
        arr_t = datetime.datetime(2024, 1, 1, hr, mn) + datetime.timedelta(minutes=dur_m)
        results.append({
            "airline":  al["name"],
            "code":     al["code"],
            "price":    price,
            "dep":      dep,
            "dep_hour": hr,
            "arr":      arr_t.strftime("%H:%M"),
            "duration": f"{dur_m//60}h {dur_m%60:02d}m",
            "dur_mins": dur_m,
            "stops":    "Non-stop" if dur_m < 100 else "1 Stop",
        })
    return sorted(results, key=lambda x: x["price"])

def query_price_history_df(route_id):
    try:
        from boto3.dynamodb.conditions import Key
        res = dynamodb_table(PRICE_HISTORY_TABLE).query(
            KeyConditionExpression=Key("RouteId").eq(str(route_id))
        )
        items = to_float(res.get("Items", []))
        local_items = [
            item for item in load_items("price_history")
            if item.get("RouteId") == str(route_id)
        ]
        items.extend(local_items)
        if items:
            items = list({
                (item["RouteId"], item["Timestamp"]): item for item in items
            }.values())
            df = pd.DataFrame(items)
            df["Price"]     = df["Price"].astype(float)
            df["Timestamp"] = pd.to_datetime(df["Timestamp"])
            return df.sort_values("Timestamp")
    except Exception as error:
        logger.warning("Could not query price history for %s: %s", route_id, error)
    items = [item for item in load_items("price_history") if item.get("RouteId") == str(route_id)]
    if items:
        df = pd.DataFrame(items)
        df["Price"] = df["Price"].astype(float)
        df["Timestamp"] = pd.to_datetime(df["Timestamp"])
        return df.sort_values("Timestamp")
    return pd.DataFrame(columns=["Timestamp", "Price"])

def evaluate_and_alert(tracker, current_price, airline):
    if tracker.get("Status") == "Paused":
        return False
    target = float(tracker["TargetPrice"])
    if current_price <= target:
        route_info = {
            "RouteId":      tracker["RouteId"],
            "Origin":       tracker["Origin"],
            "Destination":  tracker["Destination"],
            "DepartureDate":tracker["DepartureDate"],
            "TargetPrice":  target,
        }
        price_info = {
            "RouteId":   tracker["RouteId"],
            "Price":     current_price,
            "Airline":   airline,
            "Timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        sent, _ = send_sns_price_alert(tracker["UserId"], route_info, price_info)
        return sent
    return False

# ── Authentication gate ───────────────────────────────────────────────────────
auth.show_auth_page()

# ── session_state bootstrap ───────────────────────────────────────────────────
if "trackers" not in st.session_state:
    st.session_state["trackers"] = load_db_trackers()
if "search_results" not in st.session_state:
    st.session_state["search_results"] = None
if "search_meta" not in st.session_state:
    st.session_state["search_meta"] = {}
if "selected_currency" not in st.session_state:
    st.session_state["selected_currency"] = "INR"

sel_curr = st.session_state["selected_currency"]

# ── sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.image("https://www.gstatic.com/images/branding/product/2x/google_flights_64dp.png", width=48)
    st.markdown("## ✈️ Flight Monitor")
    st.caption("Serverless AWS Price Alerts")
    st.markdown("---")

    # Show who is logged in
    user = auth.current_user()
    if user:
        st.markdown(f"👤 **{user['DisplayName']}**")
        st.caption(user["Email"])
        st.markdown("---")

    # Feature 2: Currency Selector
    st.markdown("### 💱 Currency Preferences")
    curr_choice = st.selectbox(
        "Display Currency",
        get_supported_currencies(),
        index=get_supported_currencies().index(sel_curr),
        help="Select your preferred currency for display across search, trackers, and reports."
    )
    if curr_choice != sel_curr:
        st.session_state["selected_currency"] = curr_choice
        st.rerun()

    st.markdown("---")
    n = len(st.session_state["trackers"])
    st.metric("Active Trackers", n)
    st.markdown(f"**AWS Region:** `{AWS_REGION}`")
    st.markdown(
        "**SNS Topic:** `Configured` 🟢" if SNS_TOPIC_ARN
        else "**SNS Topic:** `Not configured` 🔴"
    )
    if st.button("Sign out"):
        auth.logout()
    if st.button("🔄 Sync Trackers"):
        st.session_state["trackers"] = load_db_trackers()
        st.toast("Refreshed trackers from DynamoDB and local storage.")


# ── main title ────────────────────────────────────────────────────────────────
st.markdown("# ✈️ Google Flights – Price Drop Monitor")
st.caption("Search flights · Set alerts · Analytics & Trends · Automated Email Alerts")
st.markdown("---")

tab1, tab2, tab3 = st.tabs([
    "🔍 Search Flights",
    f"🔔 My Trackers ({len(st.session_state['trackers'])})",
    "⚡ Mock Data Injector",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – Search Flights & Set Tracker (with Feature 3: Advanced Filtering & Sorting)
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Search Flights")

    c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
    with c1:
        origin = st.selectbox("From", list(AIRPORTS.keys()),
                              format_func=lambda x: f"{x} – {AIRPORTS[x]}")
    with c2:
        dest_opts = [k for k in AIRPORTS if k != origin]
        dest = st.selectbox("To", dest_opts,
                            format_func=lambda x: f"{x} – {AIRPORTS[x]}")
    with c3:
        dep_date = st.date_input("Departure", value=datetime.date.today() + datetime.timedelta(days=14))
    with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Search", use_container_width=True)

    if search_clicked:
        with st.spinner("Searching available flights..."):
            flights = mock_flights(origin, dest, str(dep_date))
            st.session_state["search_results"] = flights
            st.session_state["search_meta"] = {
                "origin": origin, "dest": dest, "date": str(dep_date)
            }

    results = st.session_state["search_results"]
    meta    = st.session_state["search_meta"]

    if results:
        o, d = meta["origin"], meta["dest"]
        st.markdown(f"### {AIRPORTS[o]} ({o}) &nbsp;→&nbsp; {AIRPORTS[d]} ({d}) &nbsp;·&nbsp; {meta['date']}")
        
        # ── Feature 3: Advanced Flight Filtering & Sorting Controls ─────────────
        with st.expander("🛠️ Filter & Sort Options", expanded=True):
            fcol1, fcol2, fcol3, fcol4 = st.columns(4)
            with fcol1:
                all_prices = [f["price"] for f in results]
                max_price_limit = max(all_prices) if all_prices else 20000
                min_price_limit = min(all_prices) if all_prices else 1000
                price_filter = st.slider(
                    "Max Price (INR ₹)",
                    min_value=min_price_limit,
                    max_value=max_price_limit + 1000,
                    value=max_price_limit + 1000,
                    step=500
                )
            with fcol2:
                airlines_avail = sorted(list(set(f["airline"] for f in results)))
                selected_airlines = st.multiselect(
                    "Filter Airlines",
                    options=airlines_avail,
                    default=airlines_avail
                )
            with fcol3:
                stops_filter = st.selectbox("Stops", ["All", "Non-stop", "1 Stop"])
            with fcol4:
                sort_by = st.selectbox("Sort By", [
                    "Price: Low to High", "Price: High to Low", "Duration", "Departure Time"
                ])

        # Apply Filters
        filtered_results = [
            f for f in results
            if f["price"] <= price_filter
            and f["airline"] in selected_airlines
            and (stops_filter == "All" or f["stops"] == stops_filter)
        ]

        # Apply Sorting
        if sort_by == "Price: Low to High":
            filtered_results.sort(key=lambda x: x["price"])
        elif sort_by == "Price: High to Low":
            filtered_results.sort(key=lambda x: x["price"], reverse=True)
        elif sort_by == "Duration":
            filtered_results.sort(key=lambda x: x["dur_mins"])
        elif sort_by == "Departure Time":
            filtered_results.sort(key=lambda x: x["dep_hour"])

        st.caption(f"Showing {len(filtered_results)} of {len(results)} flights · Prices shown in **{sel_curr}**")
        st.markdown("---")

        for fl in filtered_results:
            with st.container():
                col_al, col_time, col_type, col_price, col_btn = st.columns([2, 2.5, 1.5, 2, 1.5])
                with col_al:
                    st.markdown(f"**{fl['airline']}** `{fl['code']}`")
                with col_time:
                    st.markdown(f"🛫 `{fl['dep']}`  →  🛬 `{fl['arr']}`")
                    st.caption(fl["duration"])
                with col_type:
                    st.markdown(fl["stops"])
                with col_price:
                    # Feature 2: Currency formatting
                    formatted_p = format_currency(fl['price'], sel_curr)
                    st.markdown(f"<span class='price-big'>{formatted_p}</span>", unsafe_allow_html=True)
                with col_btn:
                    if st.button("🔔 Alert me", key=f"alert_{fl['airline']}_{fl['price']}"):
                        st.session_state["prefill_price"] = fl["price"]
                        st.session_state["prefill_airline"] = fl["airline"]

            st.markdown("<hr style='margin:.25rem 0; border-color:#3c4043'>", unsafe_allow_html=True)

        st.markdown("---")
        # ── Set Price Alert form ───────────────────────────────────────────────
        st.subheader("🔔 Set a Price Drop Alert for this Route")
        st.caption("We'll automatically email you the moment fares fall below your target price.")

        prefill_price = st.session_state.get("prefill_price", results[0]["price"])

        with st.form("alert_form"):
            fa, fb = st.columns(2)
            with fa:
                _current_user = auth.current_user()
                alert_email = st.text_input(
                    "Your email",
                    value=_current_user["Email"] if _current_user else "",
                    disabled=bool(_current_user),
                    help="Alerts will be sent to the email you signed up with.",
                )
                alert_price = st.number_input(
                    "Target price threshold (₹ INR)",
                    min_value=500, max_value=50000,
                    value=int(prefill_price), step=250,
                    help="You'll be alerted when any fare hits this price or lower."
                )
            with fb:
                st.markdown(f"**Route:** `{o}` → `{d}`")
                st.markdown(f"**Date:** `{meta['date']}`")
                st.markdown(f"**Target Threshold ({sel_curr}):** {format_currency(alert_price, sel_curr)}")
                st.markdown(f"**Cheapest fare right now:** {format_currency(results[0]['price'], sel_curr)} ({results[0]['airline']})")

            track_btn = st.form_submit_button("🚀 Start Tracking", use_container_width=True)

        if track_btn:
            route_id = f"TRK-{uuid.uuid4().hex[:8].upper()}"
            now_str  = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            tracker  = {
                "RouteId":      route_id,
                "UserId":       alert_email,
                "Origin":       o,
                "Destination":  d,
                "DepartureDate":meta["date"],
                "TargetPrice":  float(alert_price),
                "Status":       "Active",
                "CreatedAt":    now_str,
            }

            database_saved = save_tracker_db(tracker)
            st.session_state["trackers"] = load_db_trackers()

            cheapest = results[0]
            write_price_history(route_id, cheapest["price"], cheapest["airline"])

            st.success(f"✅ Tracker active! Monitoring `{o} → {d}` for fares ≤ {format_currency(alert_price, sel_curr)}")
            if not database_saved:
                st.warning("AWS is unavailable; this tracker was saved locally on this app server.")
            if cheapest["price"] <= alert_price:
                sent = evaluate_and_alert(tracker, cheapest["price"], cheapest["airline"])
                if sent:
                    st.balloons()
                    st.success(f"🎉 Alert sent immediately! Current fare {format_currency(cheapest['price'], sel_curr)} is below target. Check `{alert_email}`.")
                else:
                    st.warning("The email was not sent. Confirm the SNS email subscription and check SNS_TOPIC_ARN.")
            else:
                st.info(f"👀 Current cheapest fare is {format_currency(cheapest['price'], sel_curr)}. You'll be emailed when it drops to target or below.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – My Trackers & Analytics Dashboard (Features 1, 2, 4, 5)
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    trackers = st.session_state["trackers"]
    st.subheader(f"My Active Trackers  ({len(trackers)})")

    # Feature 5: CSV Report Export Header
    if trackers:
        with st.expander("📥 Export Trackers & Price History Reports (CSV)", expanded=False):
            # Pre-calculate analytics for export
            analytics_map = {}
            for t in trackers:
                rid = t.get("RouteId")
                df_hist = query_price_history_df(rid)
                records = df_hist.to_dict("records") if not df_hist.empty else []
                analytics_map[rid] = calculate_route_analytics(records, t.get("TargetPrice"))

            exp_col1, exp_col2 = st.columns(2)
            with exp_col1:
                csv_trackers = export_trackers_to_csv(trackers, analytics_map)
                st.download_button(
                    label="📄 Download Active Trackers Summary (.csv)",
                    data=csv_trackers,
                    file_name=f"flight_trackers_report_{datetime.date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with exp_col2:
                all_records = []
                for t in trackers:
                    df_h = query_price_history_df(t.get("RouteId"))
                    if not df_h.empty:
                        all_records.extend(df_h.to_dict("records"))
                csv_history = export_price_history_to_csv(all_records)
                st.download_button(
                    label="📊 Download Price History Ledger (.csv)",
                    data=csv_history,
                    file_name=f"price_history_ledger_{datetime.date.today()}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    if not trackers:
        st.info("No trackers yet. Search a route in the first tab and hit **Start Tracking**.")
    else:
        for i, t in enumerate(trackers):
            route_id  = t.get("RouteId", "N/A")
            origin    = t.get("Origin",      "?")
            dest      = t.get("Destination", "?")
            target    = float(t.get("TargetPrice", 0))
            status    = t.get("Status", "Active")
            email     = t.get("UserId", t.get("email", "?"))
            dep_date  = t.get("DepartureDate", "?")

            df_history = query_price_history_df(route_id)
            history_records = df_history.to_dict("records") if not df_history.empty else []
            
            # Feature 1: Price Analytics calculation
            analytics = calculate_route_analytics(history_records, target)
            curr      = analytics["current_price"]
            met       = analytics["target_met"]

            status_badge = "⏸️ PAUSED" if status == "Paused" else ("🎯 TARGET MET" if met else "👀 Monitoring")
            
            with st.expander(
                f"✈️  {origin} → {dest}   |   Target {format_currency(target, sel_curr)}   |   {status_badge}",
                expanded=True
            ):
                left, right = st.columns([1.2, 1.8])
                with left:
                    st.markdown(f"**Route ID:** `{route_id}`")
                    st.markdown(f"**Departure:** {dep_date}")
                    st.markdown(f"**Alert email:** `{email}`")
                    
                    # Status badge
                    if status == "Paused":
                        st.markdown("<span class='badge-gray'>⏸️ Tracker Paused</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("<span class='badge-blue'>🟢 Monitoring Active</span>", unsafe_allow_html=True)

                    if curr > 0:
                        st.markdown(f"**Latest Fare:** {format_currency(curr, sel_curr)} ({analytics['cheapest_airline']})")
                        if met:
                            st.markdown("<span class='badge-green'>🎯 TARGET PRICE MET</span>", unsafe_allow_html=True)
                        else:
                            diff = curr - target
                            st.markdown(f"<span class='badge-yellow'>+{format_currency(diff, sel_curr)} above target</span>", unsafe_allow_html=True)
                    else:
                        st.markdown("*No price data yet – inject data in Tab 3*")

                    st.markdown("---")
                    
                    # Feature 4: Tracker Lifecycle Controls (Pause/Resume, Edit Target, Delete)
                    st.caption("⚙️ Tracker Controls")
                    ctl_col1, ctl_col2, ctl_col3 = st.columns(3)
                    
                    with ctl_col1:
                        btn_label = "▶️ Resume" if status == "Paused" else "⏸️ Pause"
                        new_st = "Active" if status == "Paused" else "Paused"
                        if st.button(btn_label, key=f"pause_{route_id}"):
                            t["Status"] = new_st
                            update_tracker_status(route_id, new_st)
                            save_tracker_db(t)
                            st.session_state["trackers"] = load_db_trackers()
                            st.toast(f"Tracker {route_id} is now {new_st}.")
                            st.rerun()

                    with ctl_col2:
                        if st.button("📩 Alert Check", key=f"check_{route_id}"):
                            if status == "Paused":
                                st.warning("Tracker is paused. Resume it to send alerts.")
                            elif curr > 0 and curr <= target:
                                sent = evaluate_and_alert(t, curr, analytics["cheapest_airline"])
                                if sent:
                                    st.success(f"📩 Alert sent to `{email}`!")
                                else:
                                    st.warning("Alert trigger failed. Check SNS configuration.")
                            else:
                                st.info(f"Fare {format_currency(curr, sel_curr)} is above target threshold.")

                    with ctl_col3:
                        if st.button("🗑️ Delete", key=f"del_{route_id}"):
                            delete_tracker(route_id)
                            st.session_state["trackers"] = load_db_trackers()
                            st.toast(f"Deleted tracker {route_id}")
                            st.rerun()

                    # Edit Target Price Form
                    with st.popover("✏️ Edit Target Price"):
                        new_target_val = st.number_input(
                            "New Target Price (₹ INR)",
                            min_value=500, max_value=50000,
                            value=int(target), step=250,
                            key=f"input_target_{route_id}"
                        )
                        if st.button("Save New Target", key=f"save_target_{route_id}"):
                            t["TargetPrice"] = float(new_target_val)
                            update_tracker_target_price(route_id, new_target_val)
                            save_tracker_db(t)
                            st.session_state["trackers"] = load_db_trackers()
                            st.success(f"Updated target price to {format_currency(new_target_val, sel_curr)}")
                            st.rerun()

                with right:
                    # Feature 1: Detailed Analytics Cards
                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        st.metric("Lowest Fare", format_currency(analytics["min_price"], sel_curr))
                    with m2:
                        st.metric("Highest Fare", format_currency(analytics["max_price"], sel_curr))
                    with m3:
                        st.metric("Avg Fare", format_currency(analytics["avg_price"], sel_curr))
                    with m4:
                        pct = analytics["price_change_pct"]
                        trend_icon = "📉" if analytics["trend"] == "DROPPING" else ("📈" if analytics["trend"] == "RISING" else "➡️")
                        st.metric("Price Trend", f"{trend_icon} {pct:+.1f}%", f"Vol: {analytics['volatility']}")

                    if not df_history.empty:
                        # Convert chart display prices according to selected currency
                        df_chart = df_history.copy()
                        df_chart["DisplayPrice"] = df_chart["Price"].apply(lambda p: convert_currency(p, sel_curr))
                        st.caption(f"Price history chart ({sel_curr})")
                        st.line_chart(df_chart.set_index("Timestamp")["DisplayPrice"], height=170)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 – Mock Data Injector
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("⚡ Mock Data Injector")
    st.markdown(
        "Simulate flight prices and inject them into the selected route's price history. "
        "A matching fare triggers an email alert if the route's SNS email subscription is confirmed."
    )

    trackers_now = st.session_state["trackers"]

    st.markdown("### 1. Inject Flights into a Tracked Route")
    if not trackers_now:
        st.warning("Create at least one tracker first (Tab 1).")
    else:
        route_labels = {
            t["RouteId"]: f"{t['Origin']} → {t['Destination']}  ({t['RouteId']})"
            for t in trackers_now
        }
        sel_id = st.selectbox("Select Tracker / Route", list(route_labels.keys()),
                              format_func=lambda x: route_labels[x])
        sel_t  = next(t for t in trackers_now if t["RouteId"] == sel_id)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            inj_airlines = st.multiselect(
                "Airlines to include",
                [a["name"] for a in AIRLINES],
                default=[a["name"] for a in AIRLINES],
            )
        with col_b:
            pmin = st.number_input("Min price (₹)", min_value=500, max_value=20000, value=2500, step=500)
            pmax = st.number_input("Max price (₹)", min_value=1000, max_value=50000, value=7000, step=500)
        with col_c:
            n_records = st.slider("Number of records", 3, 30, 8)
            spread_hours = st.slider("Time spread (hours back)", 6, 72, 24)

        if st.button("🚀 Generate & Inject Records", use_container_width=True):
            if not inj_airlines:
                st.error("Select at least one airline.")
            elif pmin >= pmax:
                st.error("Min price must be less than Max price.")
            else:
                injected = []
                now_utc  = datetime.datetime.now(datetime.timezone.utc)
                latest = get_latest_price_history(sel_id)
                now_utc = now_utc.replace(microsecond=0)
                try:
                    latest_timestamp = datetime.datetime.fromisoformat(
                        latest.get("Timestamp", "").replace("Z", "+00:00")
                    ).astimezone(datetime.timezone.utc).replace(microsecond=0)
                    end_utc = max(now_utc, latest_timestamp + datetime.timedelta(seconds=1))
                except (ValueError, TypeError):
                    end_utc = now_utc

                start_utc = end_utc - datetime.timedelta(hours=spread_hours)
                injected_ok = 0
                for i in range(n_records):
                    al    = random.choice(inj_airlines)
                    price = random.randint(int(pmin), int(pmax))
                    fraction = i / max(n_records - 1, 1)
                    ts = start_utc + (end_utc - start_utc) * fraction
                    ts_str= ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                    saved, _ = write_price_history(sel_id, price, al, timestamp=ts_str)
                    if saved:
                        injected_ok += 1
                    injected.append({"Airline": al, "Price": price, "Timestamp": ts_str})

                if injected_ok == n_records:
                    st.success(f"✅ Injected {n_records} price records for `{sel_id}`!")
                else:
                    st.error(f"Only {injected_ok} of {n_records} price records were saved. Check AWS table access.")
                st.dataframe(
                    pd.DataFrame(sorted(injected, key=lambda x: x["Price"])),
                    use_container_width=True
                )

                st.markdown("#### 🔍 Auto-evaluating this tracker...")
                alerts_sent = 0
                latest = get_latest_price_history(sel_id)
                cp = float(latest.get("Price", 0) or 0)
                al_name = latest.get("Airline", "—")
                if cp > 0 and cp <= float(sel_t["TargetPrice"]):
                    sent = evaluate_and_alert(sel_t, cp, al_name)
                    if sent:
                        alerts_sent += 1
                        st.success(
                            f"📩 **Alert sent** · `{sel_t['Origin']}→{sel_t['Destination']}` · "
                            f"{format_currency(cp, sel_curr)} ≤ target {format_currency(sel_t['TargetPrice'], sel_curr)} · → `{sel_t['UserId']}`"
                        )
                    else:
                        st.warning(
                            "The fare met this tracker, but no email was sent. Confirm the SNS "
                            "subscription email in the tracker inbox and configure SNS_TOPIC_ARN."
                        )

                if alerts_sent == 0:
                    if cp > float(sel_t["TargetPrice"]):
                        st.info("The latest fare is above this tracker's target. Try injecting a lower price.")
                else:
                    st.balloons()

    st.markdown("---")

    st.markdown("### 2. Seed All Tracked Routes at Once")
    st.caption("Injects one random fare record per route for every active tracker.")
    if st.button("🌐 Seed All Routes with Random Fares", use_container_width=True):
        if not trackers_now:
            st.warning("No trackers found.")
        else:
            for t in trackers_now:
                base  = BASE_FARES.get((t["Origin"], t["Destination"]), 5000)
                price = round(base * random.uniform(0.80, 1.25) / 50) * 50
                al    = random.choice(AIRLINES)["name"]
                saved, error = write_price_history(t["RouteId"], price, al)
                if not saved:
                    st.error(f"Could not save fare for `{t['RouteId']}`: {error}")
                    continue
                st.write(f"&nbsp;&nbsp;✅ `{t['RouteId']}` ({t['Origin']}→{t['Destination']}) – {format_currency(price, sel_curr)} ({al})")
            st.success("Seeded all routes. Switch to **My Trackers** tab to see updated prices.")

st.markdown("---")
st.caption("Cloud-Based Flight Price Monitoring · AWS (DynamoDB · SNS · Lambda · EventBridge)")
