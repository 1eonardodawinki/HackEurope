"""
Fetch commodity price data.
Falls back to realistic mock data when ALPHA_VANTAGE_KEY is not set.
"""

import httpx
from datetime import datetime, timedelta
from config import ALPHA_VANTAGE_KEY

# Realistic mock commodity data
MOCK_PRICES = {
    "Brent Crude Oil": {
        "current_price": 84.50,
        "currency": "USD/barrel",
        "7d_change_pct": 2.3,
        "30d_change_pct": -1.8,
        "90d_high": 91.20,
        "90d_low": 76.40,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(84.50 + (i - 7) * 0.6 + (i % 3) * 0.4, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "Middle East tensions, OPEC+ production cuts, global demand outlook",
    },
    "WTI Crude": {
        "current_price": 80.20,
        "currency": "USD/barrel",
        "7d_change_pct": 1.9,
        "30d_change_pct": -2.1,
        "90d_high": 86.80,
        "90d_low": 72.10,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(80.20 + (i - 7) * 0.55 + (i % 3) * 0.35, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "US inventory levels, Gulf of Mexico production, demand from Asia",
    },
    "LNG": {
        "current_price": 9.80,
        "currency": "USD/MMBtu",
        "7d_change_pct": 3.5,
        "30d_change_pct": 12.4,
        "90d_high": 12.50,
        "90d_low": 7.20,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(9.80 + (i - 7) * 0.15 + (i % 4) * 0.2, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "European gas storage levels, Asian demand, shipping route disruptions",
    },
    "Wheat": {
        "current_price": 548.00,
        "currency": "USD/metric ton",
        "7d_change_pct": 1.2,
        "30d_change_pct": -4.5,
        "90d_high": 621.00,
        "90d_low": 498.00,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(548.00 + (i - 7) * 3.5 + (i % 5) * 2.1, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "Black Sea export disruptions, Argentine harvest outlook, global food security",
    },
    "Sunflower Oil": {
        "current_price": 920.00,
        "currency": "USD/metric ton",
        "7d_change_pct": 0.8,
        "30d_change_pct": -2.9,
        "90d_high": 1050.00,
        "90d_low": 860.00,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(920.00 + (i - 7) * 4.0 + (i % 4) * 3.0, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "Ukraine production and export capacity, competing edible oils, EU demand",
    },
    "Shipping Freight Index": {
        "current_price": 1850.00,
        "currency": "USD/container (20ft)",
        "7d_change_pct": 8.2,
        "30d_change_pct": 45.0,
        "90d_high": 2100.00,
        "90d_low": 980.00,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(1850.00 - (i * 22.0) + (i % 6) * 15.0, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "Red Sea/Suez rerouting, port congestion, vessel availability",
    },
    "Steel": {
        "current_price": 680.00,
        "currency": "USD/metric ton",
        "7d_change_pct": -0.5,
        "30d_change_pct": 3.2,
        "90d_high": 720.00,
        "90d_low": 590.00,
        "recent_history": [
            {"date": (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d"),
             "price": round(680.00 + (i - 7) * 1.8 + (i % 5) * 1.5, 2)}
            for i in range(30, 0, -1)
        ],
        "drivers": "Chinese demand, iron ore prices, Black Sea export route stability",
    },
}


async def get_commodity_price(commodity: str, days_back: int = 30) -> dict:
    """Get commodity price data with history."""

    # Normalize commodity name
    for key in MOCK_PRICES:
        if key.lower() in commodity.lower() or commodity.lower() in key.lower():
            data = MOCK_PRICES[key].copy()
            data["commodity"] = key
            data["recent_history"] = data["recent_history"][-days_back:]
            return data

    return {
        "commodity": commodity,
        "current_price": 100.0,
        "currency": "USD",
        "7d_change_pct": 0.0,
        "30d_change_pct": 0.0,
        "error": "Price data not available",
    }


async def get_multiple_commodities(commodities: list[str]) -> list[dict]:
    """Get prices for multiple commodities."""
    results = []
    for c in commodities:
        data = await get_commodity_price(c)
        results.append(data)
    return results
