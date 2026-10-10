"""
test_features.py
----------------
Comprehensive test suite verifying the 5 newly implemented features for Google Flights Price Monitor:
1. Price Analytics & Trend Engine
2. Multi-Currency Converter
3. Advanced Flight Search Filtering & Sorting
4. Tracker Lifecycle Management (Edit, Pause/Resume, Delete)
5. Automated Data Export (CSV Export)
"""

import unittest
import os
import json
import tempfile
from unittest.mock import patch

from src.utils.currency import (
    convert_currency, format_currency, get_supported_currencies, get_currency_symbol
)
from src.processor.analytics import (
    calculate_route_analytics, export_trackers_to_csv, export_price_history_to_csv
)
from src.database.local_store import (
    update_tracker_status, update_tracker_target_price, delete_tracker,
    save_items, load_items
)
from src.frontend.app import mock_flights
import src.api_fetcher.fetcher as fetcher
import src.processor.alert_engine as alert_engine


class TestCurrencyConverter(unittest.TestCase):
    """Test Feature 2: Multi-Currency Conversion & Formatting."""

    def test_supported_currencies(self):
        currencies = get_supported_currencies()
        self.assertIn("INR", currencies)
        self.assertIn("USD", currencies)
        self.assertIn("EUR", currencies)
        self.assertIn("GBP", currencies)
        self.assertIn("AED", currencies)

    def test_convert_currency(self):
        inr_val = 10000.0
        usd_val = convert_currency(inr_val, "USD")
        self.assertEqual(usd_val, 120.0)

        eur_val = convert_currency(inr_val, "EUR")
        self.assertEqual(eur_val, 110.0)

    def test_format_currency(self):
        self.assertEqual(format_currency(5000, "INR"), "₹5,000")
        self.assertEqual(format_currency(5000, "USD"), "$60.00")
        self.assertEqual(format_currency(5000, "EUR"), "€55.00")


class TestPriceAnalytics(unittest.TestCase):
    """Test Feature 1: Price Analytics & Trend Calculations."""

    def test_empty_analytics(self):
        analytics = calculate_route_analytics([])
        self.assertEqual(analytics["total_observations"], 0)
        self.assertEqual(analytics["current_price"], 0.0)
        self.assertEqual(analytics["trend"], "STABLE")

    def test_route_analytics_metrics(self):
        history = [
            {"Price": 5000.0, "Timestamp": "2026-10-10T10:00:00Z", "Airline": "IndiGo"},
            {"Price": 4800.0, "Timestamp": "2026-10-10T11:00:00Z", "Airline": "Air India"},
            {"Price": 4200.0, "Timestamp": "2026-10-10T12:00:00Z", "Airline": "Akasa Air"},
        ]
        target_price = 4500.0

        analytics = calculate_route_analytics(history, target_price)

        self.assertEqual(analytics["min_price"], 4200.0)
        self.assertEqual(analytics["max_price"], 5000.0)
        self.assertEqual(analytics["avg_price"], 4666.67)
        self.assertEqual(analytics["current_price"], 4200.0)
        self.assertEqual(analytics["trend"], "DROPPING")
        self.assertTrue(analytics["target_met"])
        self.assertEqual(analytics["cheapest_airline"], "Akasa Air")


class TestCSVExport(unittest.TestCase):
    """Test Feature 5: Automated CSV Export Engine."""

    def test_export_trackers_to_csv(self):
        trackers = [
            {
                "RouteId": "TRK-101",
                "Origin": "TRV",
                "Destination": "BLR",
                "DepartureDate": "2026-10-25",
                "TargetPrice": 3500.0,
                "Status": "Active",
                "UserId": "test@example.com",
                "CreatedAt": "2026-10-10T10:00:00Z"
            }
        ]
        analytics = {
            "TRK-101": {
                "current_price": 3200.0,
                "min_price": 3100.0,
                "max_price": 3600.0,
                "avg_price": 3300.0,
                "trend": "DROPPING",
                "volatility": "Low",
                "target_met": True
            }
        }

        csv_out = export_trackers_to_csv(trackers, analytics)
        self.assertIn("TRK-101", csv_out)
        self.assertIn("TRV", csv_out)
        self.assertIn("BLR", csv_out)
        self.assertIn("DROPPING", csv_out)

    def test_export_price_history_to_csv(self):
        history = [
            {"RouteId": "TRK-101", "Timestamp": "2026-10-10T10:00:00Z", "Price": 3500.0, "Airline": "IndiGo"}
        ]
        csv_out = export_price_history_to_csv(history)
        self.assertIn("TRK-101", csv_out)
        self.assertIn("IndiGo", csv_out)


class TestTrackerLifecycle(unittest.TestCase):
    """Test Feature 4: Tracker Lifecycle Management (Edit, Pause/Resume, Delete)."""

    def setUp(self):
        self.test_tracker = {
            "RouteId": "TRK-TEST-LIFECYCLE",
            "UserId": "user@test.com",
            "Origin": "DEL",
            "Destination": "BOM",
            "DepartureDate": "2026-11-01",
            "TargetPrice": 5000.0,
            "Status": "Active",
            "CreatedAt": "2026-10-10T12:00:00Z"
        }
        save_items("trackers", [self.test_tracker])

    def test_update_tracker_status(self):
        ok = update_tracker_status("TRK-TEST-LIFECYCLE", "Paused")
        self.assertTrue(ok)
        trackers = load_items("trackers")
        t = next(tr for tr in trackers if tr["RouteId"] == "TRK-TEST-LIFECYCLE")
        self.assertEqual(t["Status"], "Paused")

    def test_update_tracker_target_price(self):
        ok = update_tracker_target_price("TRK-TEST-LIFECYCLE", 4500.0)
        self.assertTrue(ok)
        trackers = load_items("trackers")
        t = next(tr for tr in trackers if tr["RouteId"] == "TRK-TEST-LIFECYCLE")
        self.assertEqual(t["TargetPrice"], 4500.0)

    def test_delete_tracker(self):
        ok = delete_tracker("TRK-TEST-LIFECYCLE")
        self.assertTrue(ok)
        trackers = load_items("trackers")
        found = any(tr["RouteId"] == "TRK-TEST-LIFECYCLE" for tr in trackers)
        self.assertFalse(found)


class TestFlightSearchAndFiltering(unittest.TestCase):
    """Test Feature 3: Mock Flight Search & Filtering Logic."""

    def test_mock_flights_generation(self):
        flights = mock_flights("TRV", "BLR", "2026-10-25")
        self.assertTrue(len(flights) > 0)
        for fl in flights:
            self.assertIn("airline", fl)
            self.assertIn("price", fl)
            self.assertIn("duration", fl)
            self.assertIn("stops", fl)

    def test_fetcher_skips_paused_trackers(self):
        paused_tracker = {
            "RouteId": "TRK-PAUSED-001",
            "Origin": "TRV",
            "Destination": "BLR",
            "DepartureDate": "2026-10-25",
            "TargetPrice": 3000.0,
            "Status": "Paused"
        }

        with patch.object(fetcher, "scan_tracked_routes", return_value=[paused_tracker]):
            res = fetcher.lambda_handler({}, None)
            body = json.loads(res["body"])
            self.assertEqual(len(body["processed_records"]), 0)

    def test_alert_engine_skips_paused_trackers(self):
        paused_tracker = {
            "RouteId": "TRK-PAUSED-002",
            "Origin": "TRV",
            "Destination": "BLR",
            "DepartureDate": "2026-10-25",
            "TargetPrice": 3000.0,
            "Status": "Paused",
            "UserId": "test@example.com"
        }

        with patch.object(alert_engine, "get_active_tracked_routes", return_value=[paused_tracker]):
            results, alerts_sent = alert_engine.evaluate_route_price_alerts()
            self.assertEqual(alerts_sent, 0)
            self.assertEqual(results[0]["Status"], "Skipped (Tracker is Paused)")


if __name__ == "__main__":
    unittest.main()
