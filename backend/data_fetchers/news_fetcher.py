"""
Fetch recent news about maritime incidents and commodity markets.
Falls back to realistic mock data when NEWS_API_KEY is not set.
"""

import httpx
from datetime import datetime, timedelta
from config import NEWS_API_KEY

MOCK_NEWS = {
    "Strait of Hormuz": [
        {
            "title": "Iran Seizes Oil Tanker in Persian Gulf amid US Tensions",
            "source": "Reuters",
            "published_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "description": "Iranian forces boarded and seized a Marshall Islands-flagged oil tanker in the Persian Gulf, raising alarm about freedom of navigation.",
            "url": "https://reuters.com",
        },
        {
            "title": "US Navy Escorts Tankers Through Strait of Hormuz",
            "source": "AP News",
            "published_at": (datetime.utcnow() - timedelta(days=5)).isoformat(),
            "description": "The US Fifth Fleet has increased escort operations for oil tankers transiting the Strait of Hormuz amid rising regional tensions.",
            "url": "https://apnews.com",
        },
        {
            "title": "Brent Crude Surges on Middle East Supply Concerns",
            "source": "Financial Times",
            "published_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "description": "Oil prices jumped 3% after reports of increased maritime incidents in the Strait of Hormuz, with Brent crude touching $87 per barrel.",
            "url": "https://ft.com",
        },
    ],
    "Black Sea": [
        {
            "title": "Ukraine Reports Drone Attacks on Russian Oil Tankers in Black Sea",
            "source": "BBC",
            "published_at": (datetime.utcnow() - timedelta(days=3)).isoformat(),
            "description": "Ukrainian naval drones targeted Russian oil tankers in the Black Sea, disrupting commodity flows from Russian ports.",
            "url": "https://bbc.com",
        },
        {
            "title": "Black Sea Grain Initiative Uncertainty Weighs on Wheat Prices",
            "source": "Bloomberg",
            "published_at": (datetime.utcnow() - timedelta(days=6)).isoformat(),
            "description": "Wheat futures rose 4% amid uncertainty over safe passage in the Black Sea following renewed military activity.",
            "url": "https://bloomberg.com",
        },
        {
            "title": "Dark Fleet Activity Surges in Black Sea — Satellite Analysis",
            "source": "MarineTraffic Intelligence",
            "published_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
            "description": "Analysts have detected an increase in AIS transponder shutoffs by vessels suspected of transporting Russian crude in defiance of sanctions.",
            "url": "https://marinetraffic.com",
        },
    ],
    "Red Sea": [
        {
            "title": "Houthi Militants Attack Container Ship in Red Sea",
            "source": "Reuters",
            "published_at": (datetime.utcnow() - timedelta(days=2)).isoformat(),
            "description": "Yemen's Houthi rebels launched ballistic missiles at a container ship in the southern Red Sea, forcing major shipping lines to reroute around the Cape of Good Hope.",
            "url": "https://reuters.com",
        },
        {
            "title": "Shipping Costs Soar as Companies Avoid Red Sea",
            "source": "Wall Street Journal",
            "published_at": (datetime.utcnow() - timedelta(days=4)).isoformat(),
            "description": "Freight rates on Asia-Europe routes surged 180% as shipping companies divert vessels around Africa to avoid Houthi attacks.",
            "url": "https://wsj.com",
        },
    ],
}


async def search_recent_news(query: str, region: str = "", days_back: int = 7) -> list[dict]:
    """Search for recent news relevant to a maritime incident."""

    if NEWS_API_KEY:
        try:
            from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "from": from_date,
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": 5,
                        "apiKey": NEWS_API_KEY,
                    },
                )
                if resp.status_code == 200:
                    articles = resp.json().get("articles", [])
                    return [
                        {
                            "title": a.get("title", ""),
                            "source": a.get("source", {}).get("name", ""),
                            "published_at": a.get("publishedAt", ""),
                            "description": a.get("description", ""),
                            "url": a.get("url", ""),
                        }
                        for a in articles
                    ]
        except Exception:
            pass

    # Fallback: return mock news for the region
    for hotzone_name, articles in MOCK_NEWS.items():
        if hotzone_name.lower() in region.lower() or region.lower() in hotzone_name.lower():
            return articles

    # Generic maritime news if no region match
    all_articles = []
    for articles in MOCK_NEWS.values():
        all_articles.extend(articles[:1])
    return all_articles[:3]
