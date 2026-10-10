"""
analytics.py
------------
Price Analytics, Trend Indicator, and Data Export Engine for Flight Price Monitor.
Provides statistical calculations (Min/Max/Avg, Volatility, Trend, Price Drop %)
and generates CSV/JSON export data.
"""

import io
import csv
import math
import datetime
from typing import List, Dict, Any, Optional


def calculate_route_analytics(
    price_records: List[Dict[str, Any]],
    target_price: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calculate comprehensive price analytics for a route given its historical price records.
    
    Expected record format:
    [{ "Price": 4500.0, "Timestamp": "2026-10-10T12:00:00Z", "Airline": "IndiGo" }, ...]
    """
    if not price_records:
        return {
            "min_price": 0.0,
            "max_price": 0.0,
            "avg_price": 0.0,
            "current_price": 0.0,
            "first_price": 0.0,
            "price_change_amount": 0.0,
            "price_change_pct": 0.0,
            "target_difference": 0.0,
            "target_met": False,
            "trend": "STABLE",
            "volatility": "Low",
            "total_observations": 0,
            "cheapest_airline": "N/A",
        }

    # Sort records chronologically
    sorted_records = sorted(
        price_records,
        key=lambda r: str(r.get("Timestamp", ""))
    )

    prices = [float(r.get("Price", 0)) for r in sorted_records if r.get("Price") is not None]
    
    if not prices:
        return calculate_route_analytics([], target_price)

    min_price = min(prices)
    max_price = max(prices)
    avg_price = sum(prices) / len(prices)
    
    first_price = prices[0]
    current_price = prices[-1]
    
    # Cheapest airline identification
    min_record = min(sorted_records, key=lambda r: float(r.get("Price", float("inf"))))
    cheapest_airline = min_record.get("Airline", "Unknown")

    # Change calculations
    price_change_amount = current_price - first_price
    price_change_pct = ((current_price - first_price) / first_price * 100.0) if first_price > 0 else 0.0

    # Trend detection (comparing latest vs first or average)
    if price_change_pct < -2.0:
        trend = "DROPPING"
    elif price_change_pct > 2.0:
        trend = "RISING"
    else:
        trend = "STABLE"

    # Volatility (Standard Deviation)
    if len(prices) > 1:
        variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
        std_dev = math.sqrt(variance)
        rel_volatility = (std_dev / avg_price) * 100.0 if avg_price > 0 else 0.0
        
        if rel_volatility > 15.0:
            volatility = "High"
        elif rel_volatility > 5.0:
            volatility = "Medium"
        else:
            volatility = "Low"
    else:
        volatility = "Low"

    # Target evaluation
    target_met = False
    target_difference = 0.0
    if target_price is not None and target_price > 0:
        target_met = current_price <= target_price
        target_difference = current_price - float(target_price)

    return {
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "avg_price": round(avg_price, 2),
        "current_price": round(current_price, 2),
        "first_price": round(first_price, 2),
        "price_change_amount": round(price_change_amount, 2),
        "price_change_pct": round(price_change_pct, 2),
        "target_difference": round(target_difference, 2),
        "target_met": target_met,
        "trend": trend,
        "volatility": volatility,
        "total_observations": len(prices),
        "cheapest_airline": cheapest_airline,
    }


def export_trackers_to_csv(trackers: List[Dict[str, Any]], analytics_by_route: Optional[Dict[str, Dict]] = None) -> str:
    """
    Generate a CSV representation of all active trackers and their latest price analytics.
    """
    output = io.StringIO()
    fieldnames = [
        "RouteId", "Origin", "Destination", "DepartureDate", "TargetPrice",
        "Status", "UserId", "CreatedAt", "CurrentPrice", "MinPrice", "MaxPrice",
        "AvgPrice", "Trend", "Volatility", "TargetMet"
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for tracker in trackers:
        route_id = tracker.get("RouteId", "")
        analytics = (analytics_by_route or {}).get(route_id, {})
        
        row = {
            "RouteId": route_id,
            "Origin": tracker.get("Origin", ""),
            "Destination": tracker.get("Destination", ""),
            "DepartureDate": tracker.get("DepartureDate", ""),
            "TargetPrice": tracker.get("TargetPrice", 0.0),
            "Status": tracker.get("Status", "Active"),
            "UserId": tracker.get("UserId", tracker.get("email", "")),
            "CreatedAt": tracker.get("CreatedAt", ""),
            "CurrentPrice": analytics.get("current_price", 0.0),
            "MinPrice": analytics.get("min_price", 0.0),
            "MaxPrice": analytics.get("max_price", 0.0),
            "AvgPrice": analytics.get("avg_price", 0.0),
            "Trend": analytics.get("trend", "N/A"),
            "Volatility": analytics.get("volatility", "N/A"),
            "TargetMet": "YES" if analytics.get("target_met") else "NO"
        }
        writer.writerow(row)

    return output.getvalue()


def export_price_history_to_csv(price_records: List[Dict[str, Any]]) -> str:
    """
    Generate a CSV representation of price history observations.
    """
    output = io.StringIO()
    fieldnames = ["RouteId", "Timestamp", "Price", "Airline"]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    sorted_records = sorted(
        price_records,
        key=lambda r: (r.get("RouteId", ""), r.get("Timestamp", ""))
    )

    for record in sorted_records:
        writer.writerow({
            "RouteId": record.get("RouteId", ""),
            "Timestamp": record.get("Timestamp", ""),
            "Price": record.get("Price", 0.0),
            "Airline": record.get("Airline", "")
        })

    return output.getvalue()
