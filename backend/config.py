import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AISSTREAM_API_KEY = os.getenv("AISSTREAM_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# ── Mode ──────────────────────────────────────────────────────────────────────
# Auto-enable demo if no AISstream key is set (override with DEMO_MODE=false)
_demo_env = os.getenv("DEMO_MODE")
if _demo_env is not None:
    DEMO_MODE = _demo_env.lower() == "true"
else:
    DEMO_MODE = not bool(AISSTREAM_API_KEY)

# ── Geopolitical Hotzones ────────────────────────────────────────────────────
HOTZONES = {
    "Strait of Hormuz": {
        "min_lat": 24.5, "max_lat": 27.5,
        "min_lon": 55.0, "max_lon": 60.0,
        "center_lat": 26.0, "center_lon": 57.0,
        "commodities": ["Brent Crude Oil", "LNG", "WTI Crude"],
        "color": "#ff0044",
        "description": "Critical chokepoint for ~20% of global oil supply",
    },
    "Black Sea": {
        "min_lat": 41.0, "max_lat": 46.5,
        "min_lon": 27.0, "max_lon": 41.0,
        "center_lat": 43.5, "center_lon": 34.0,
        "commodities": ["Wheat", "Sunflower Oil", "Steel", "Brent Crude Oil"],
        "color": "#ff6b00",
        "description": "Major route for Ukrainian/Russian commodity exports",
    },
    "Red Sea": {
        "min_lat": 11.0, "max_lat": 30.0,
        "min_lon": 32.0, "max_lon": 44.0,
        "center_lat": 20.0, "center_lon": 38.0,
        "commodities": ["Brent Crude Oil", "Shipping Freight Index"],
        "color": "#ff6b00",
        "description": "Suez Canal access route — Houthi threat zone",
    },
}

# ── Detection Thresholds ──────────────────────────────────────────────────────
AIS_DROPOUT_MINUTES = 25          # Ship is "dark" after this many minutes
PROXIMITY_DISTANCE_NM = 0.4       # Nautical miles for ship-to-ship proximity
PROXIMITY_DURATION_MINUTES = 15   # How long ships must be close to flag
INCIDENT_THRESHOLD = 3            # Incidents needed to trigger intel report
INCIDENT_WINDOW_HOURS = 24        # Time window for threshold

# ── Agent Settings ───────────────────────────────────────────────────────────
MODEL = "claude-sonnet-4-6"        # Reporter (needs synthesis quality)
FAST_MODEL = "claude-haiku-4-5-20251001"  # Investigation agents + critic (speed)
MAX_CRITIC_ROUNDS = 1              # 1 round is enough; early-exit already works

# ── Demo Simulation ───────────────────────────────────────────────────────────
DEMO_SHIP_COUNT = 30
DEMO_INCIDENT_DELAY_SECONDS = 20   # First incident fires after this delay
DEMO_INCIDENT_INTERVAL_SECONDS = 25  # Subsequent incidents fire at this interval
