"""
currency.py
-----------
Multi-Currency conversion and formatting module for Google Flights Price Monitor.
Provides real-time static conversion rates relative to Base Currency (INR).
"""

CURRENCY_RATES = {
    "INR": {"rate": 1.0, "symbol": "₹", "name": "Indian Rupee"},
    "USD": {"rate": 0.012, "symbol": "$", "name": "US Dollar"},
    "EUR": {"rate": 0.011, "symbol": "€", "name": "Euro"},
    "GBP": {"rate": 0.0095, "symbol": "£", "name": "British Pound"},
    "AED": {"rate": 0.044, "symbol": "AED ", "name": "UAE Dirham"},
}

DEFAULT_CURRENCY = "INR"


def get_supported_currencies() -> list[str]:
    """Return list of supported currency codes."""
    return list(CURRENCY_RATES.keys())


def get_currency_symbol(currency: str = "INR") -> str:
    """Return symbol for currency code."""
    currency_code = currency.upper() if currency else "INR"
    return CURRENCY_RATES.get(currency_code, CURRENCY_RATES["INR"])["symbol"]


def convert_currency(amount_in_inr: float, target_currency: str = "INR") -> float:
    """
    Convert an amount in INR to the target currency.
    Returns converted amount rounded to 2 decimal places.
    """
    if amount_in_inr is None:
        return 0.0
    
    currency_code = target_currency.upper() if target_currency else "INR"
    rate = CURRENCY_RATES.get(currency_code, CURRENCY_RATES["INR"])["rate"]
    converted = float(amount_in_inr) * rate
    
    # Standard rounding based on currency
    if currency_code == "INR":
        return round(converted, 2)
    else:
        return round(converted, 2)


def format_currency(amount_in_inr: float, currency: str = "INR") -> str:
    """
    Format an amount given in INR into a localized currency string.
    Example: 5000 in USD -> "$60.00"
    """
    currency_code = currency.upper() if currency else "INR"
    symbol = get_currency_symbol(currency_code)
    converted = convert_currency(amount_in_inr, currency_code)
    
    if currency_code == "INR":
        return f"{symbol}{converted:,.0f}"
    else:
        return f"{symbol}{converted:,.2f}"
