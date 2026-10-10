# 🚀 Flight Price Monitor – 5 New Features & Technical Summary

This document summarizes the GitHub user configuration, repository synchronization, and 5 production-grade new features implemented in the **Google Flights Price Monitor** project.

---


## ✨ 1. Summary of 5 New Features Added

### Feature 1: 📊 Price Analytics & Price Trend Indicator Engine
- **Module**: [`src/processor/analytics.py`](file:///d:/balaji/src/processor/analytics.py)
- **Description**:
  - Automatically calculates historical price statistics for every tracked route: **Lowest Fare (Min)**, **Highest Fare (Max)**, and **Average Fare (Avg)**.
  - Computes dynamic **Price Change Percentage** comparing initial fare vs current price.
  - Identifies real-time fare trends (**📉 DROPPING**, **📈 RISING**, or **➡️ STABLE**) with a 2% sensitivity threshold.
  - Determines **Price Volatility Rating** (`High`, `Medium`, or `Low`) based on standard deviation across fare observations.
  - Identifies the cheapest airline across history for each route.

### Feature 2: 💱 Multi-Currency Converter & Preference Switcher
- **Module**: [`src/utils/currency.py`](file:///d:/balaji/src/utils/currency.py)
- **Description**:
  - Adds support for 5 major global currencies: **INR (₹)**, **USD ($)**, **EUR (€)**, **GBP (£)**, and **AED (AED)**.
  - Includes a real-time Currency Preference selector in the Streamlit application sidebar.
  - Dynamically converts and formats search result prices, target thresholds, metrics badges, analytics cards, and interactive charts across the user interface.

### Feature 3: 🛠️ Advanced Flight Search Filtering & Multi-Criteria Sorting
- **Module**: [`src/frontend/app.py`](file:///d:/balaji/src/frontend/app.py)
- **Description**:
  - Introduces a comprehensive Filter & Sort Toolbar for flight search results:
    - **Max Price Slider**: Filter out flights above a customizable price threshold.
    - **Airline Selector**: Multi-select filter to view specific preferred airlines (IndiGo, Air India, Vistara, Akasa Air, SpiceJet).
    - **Stops Filter**: Filter by `Non-stop` or `1 Stop`.
    - **Sorting Options**: Sort results by *Price (Low to High)*, *Price (High to Low)*, *Duration (Shortest to Longest)*, or *Departure Time (Earliest to Latest)*.

### Feature 4: ⚙️ Complete Tracker Lifecycle Management (Edit, Pause/Resume, Delete)
- **Modules**: [`src/database/local_store.py`](file:///d:/balaji/src/database/local_store.py), [`src/api_fetcher/fetcher.py`](file:///d:/balaji/src/api_fetcher/fetcher.py), [`src/processor/alert_engine.py`](file:///d:/balaji/src/processor/alert_engine.py)
- **Description**:
  - **Pause / Resume**: Users can toggle tracker monitoring status (`Active` / `Paused`). Background scheduled jobs in `fetcher.py` and `alert_engine.py` respect this status and safely skip paused routes.
  - **Edit Target Price**: Interactive popover form allowing users to update target price thresholds directly without re-creating trackers.
  - **Delete Tracker**: Delete button for removing active route trackers from local JSON storage and DynamoDB.

### Feature 5: 📥 Automated Data Export Engine (CSV Reports)
- **Module**: [`src/processor/analytics.py`](file:///d:/balaji/src/processor/analytics.py)
- **Description**:
  - Adds a dedicated **Export Trackers & Reports** section in the UI.
  - Enables one-click downloading of:
    1. **Active Trackers Summary CSV**: Complete report containing Route IDs, origin/destination, target prices, current prices, analytics, trends, volatility, and target met status.
    2. **Price History Ledger CSV**: Raw historical price observation logs with timestamps and airline names.

---

## 🧪 3. Testing & Empirical Verification

A unit test suite was implemented in [`tests/test_features.py`](file:///d:/balaji/tests/test_features.py) covering all 5 features:

- `TestCurrencyConverter`: Verified multi-currency conversion, formatting, and symbol lookup.
- `TestPriceAnalytics`: Verified Min/Max/Avg calculation, trend detection (DROPPING/RISING/STABLE), volatility, and target price evaluation.
- `TestCSVExport`: Verified CSV formatting and structure for trackers and history logs.
- `TestTrackerLifecycle`: Verified status updates (Pause/Resume), target price modification, and tracker deletion.
- `TestFlightSearchAndFiltering`: Verified flight option generation, filter logic, and status skipping in scheduled fetcher and alert engine.

### How to Run Tests Locally
```powershell
python -m unittest discover tests
```

---

## 🚀 4. Local Quickstart Guide

1. **Install Dependencies**:
   ```powershell
   python -m pip install -r requirements.txt
   ```
2. **Launch Streamlit Web App**:
   ```powershell
   python -m streamlit run src/frontend/app.py
   ```
