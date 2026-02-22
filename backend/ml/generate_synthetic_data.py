"""
Generate realistic synthetic AIS turn-off/turn-on event data.

Produces ~1300 confirmed shadow fleet ships and ~8000 unlabeled ships
with realistic feature distributions for PU Learning training.
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# --- Flag state MID codes (first 3 digits of MMSI) ---
CONVENIENCE_FLAG_MIDS = {
    "Panama": ["351", "352", "353", "354", "355", "356", "357"],
    "Liberia": ["636", "637"],
    "Marshall Islands": ["538"],
    "Cameroon": ["613"],
    "Palau": ["511"],
    "Gabon": ["626"],
    "Comoros": ["616"],
    "Tanzania": ["674"],
    "Togo": ["671"],
}

NORMAL_FLAG_MIDS = {
    "Norway": ["257", "258", "259"],
    "Greece": ["237", "239", "240", "241"],
    "Japan": ["431", "432"],
    "China": ["412", "413", "414"],
    "Singapore": ["563", "564", "565"],
    "UK": ["232", "233", "234", "235"],
    "Germany": ["211", "218"],
    "South Korea": ["440", "441"],
    "USA": ["303", "338", "366", "367", "368", "369"],
    "Denmark": ["219", "220"],
}

# --- Geographic bounding boxes ---
RUSSIAN_WATERS = [
    {"name": "Black Sea (Russian)", "min_lat": 43.0, "max_lat": 46.5, "min_lon": 36.0, "max_lon": 41.0},
    {"name": "Barents Sea", "min_lat": 68.0, "max_lat": 76.0, "min_lon": 20.0, "max_lon": 55.0},
    {"name": "Far East Russia", "min_lat": 42.0, "max_lat": 55.0, "min_lon": 130.0, "max_lon": 145.0},
]

STS_ZONES = [
    {"name": "Ceuta", "center_lat": 35.89, "center_lon": -5.32, "radius_deg": 0.3},
    {"name": "Kalamata", "center_lat": 36.95, "center_lon": 22.11, "radius_deg": 0.4},
    {"name": "Laconian Gulf", "center_lat": 36.5, "center_lon": 22.8, "radius_deg": 0.3},
    {"name": "Strait of Hormuz", "min_lat": 24.5, "max_lat": 27.5, "min_lon": 55.0, "max_lon": 60.0},
]

GLOBAL_WATERS = [
    {"name": "North Atlantic", "min_lat": 30.0, "max_lat": 55.0, "min_lon": -40.0, "max_lon": -5.0},
    {"name": "Mediterranean", "min_lat": 30.0, "max_lat": 42.0, "min_lon": -5.0, "max_lon": 36.0},
    {"name": "Indian Ocean", "min_lat": -10.0, "max_lat": 25.0, "min_lon": 50.0, "max_lon": 80.0},
    {"name": "South China Sea", "min_lat": 0.0, "max_lat": 23.0, "min_lon": 105.0, "max_lon": 120.0},
    {"name": "West Africa", "min_lat": -5.0, "max_lat": 15.0, "min_lon": -20.0, "max_lon": 5.0},
]

VESSEL_CLASSES = ["tanker", "cargo", "bulk_carrier", "container", "fishing", "passenger", "other"]
SIZE_CATEGORIES = ["small", "medium", "large", "VLCC"]


def _random_mmsi(rng: np.random.Generator, mid_prefix: str) -> str:
    """Generate a 9-digit MMSI with given MID prefix."""
    remaining = 9 - len(mid_prefix)
    suffix = "".join(str(rng.integers(0, 10)) for _ in range(remaining))
    return mid_prefix + suffix


def _random_point_in_bbox(rng: np.random.Generator, bbox: dict) -> tuple[float, float]:
    """Random lat/lon within a bounding box."""
    lat = rng.uniform(bbox["min_lat"], bbox["max_lat"])
    lon = rng.uniform(bbox["min_lon"], bbox["max_lon"])
    return round(lat, 4), round(lon, 4)


def _random_point_near_center(rng: np.random.Generator, zone: dict) -> tuple[float, float]:
    """Random lat/lon near a center point with given radius."""
    angle = rng.uniform(0, 2 * np.pi)
    r = zone["radius_deg"] * np.sqrt(rng.uniform(0, 1))
    lat = zone["center_lat"] + r * np.cos(angle)
    lon = zone["center_lon"] + r * np.sin(angle)
    return round(lat, 4), round(lon, 4)


def _pick_flag(rng: np.random.Generator, convenience_prob: float) -> tuple[str, str]:
    """Pick a flag and return (flag_name, mid_prefix)."""
    if rng.random() < convenience_prob:
        flag = rng.choice(list(CONVENIENCE_FLAG_MIDS.keys()))
        mid = rng.choice(CONVENIENCE_FLAG_MIDS[flag])
    else:
        flag = rng.choice(list(NORMAL_FLAG_MIDS.keys()))
        mid = rng.choice(NORMAL_FLAG_MIDS[flag])
    return flag, mid


def _pick_location_shadow(rng: np.random.Generator) -> tuple[float, float]:
    """Pick a location biased toward shadow fleet activity areas."""
    r = rng.random()
    if r < 0.40:
        bbox = rng.choice(RUSSIAN_WATERS)
        return _random_point_in_bbox(rng, bbox)
    elif r < 0.70:
        zone = rng.choice(STS_ZONES)
        if "center_lat" in zone:
            return _random_point_near_center(rng, zone)
        return _random_point_in_bbox(rng, zone)
    else:
        bbox = rng.choice(GLOBAL_WATERS)
        return _random_point_in_bbox(rng, bbox)


def _pick_location_normal(rng: np.random.Generator) -> tuple[float, float]:
    """Pick a location with normal shipping distribution."""
    r = rng.random()
    if r < 0.08:
        bbox = rng.choice(RUSSIAN_WATERS)
        return _random_point_in_bbox(rng, bbox)
    elif r < 0.15:
        zone = rng.choice(STS_ZONES)
        if "center_lat" in zone:
            return _random_point_near_center(rng, zone)
        return _random_point_in_bbox(rng, zone)
    else:
        bbox = rng.choice(GLOBAL_WATERS)
        return _random_point_in_bbox(rng, bbox)


def generate_shadow_fleet_mmsis(
    n: int = 1300,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate n confirmed shadow fleet ship identities."""
    rng = np.random.default_rng(seed)
    ships = []

    for i in range(n):
        flag, mid = _pick_flag(rng, convenience_prob=0.80)
        mmsi = _random_mmsi(rng, mid)
        vessel_class = rng.choice(
            VESSEL_CLASSES,
            p=[0.85, 0.08, 0.03, 0.01, 0.01, 0.01, 0.01],
        )
        size_cat = rng.choice(
            SIZE_CATEGORIES,
            p=[0.05, 0.20, 0.45, 0.30],
        )
        ships.append({
            "mmsi": mmsi,
            "flag": flag,
            "vessel_class": vessel_class,
            "size_category": size_cat,
            "label": 1,
        })

    return pd.DataFrame(ships)


def generate_unlabeled_mmsis(
    n: int = 8000,
    seed: int = 123,
) -> pd.DataFrame:
    """Generate n unlabeled ship identities."""
    rng = np.random.default_rng(seed)
    ships = []

    for i in range(n):
        flag, mid = _pick_flag(rng, convenience_prob=0.30)
        vessel_class = rng.choice(
            VESSEL_CLASSES,
            p=[0.30, 0.25, 0.15, 0.15, 0.08, 0.04, 0.03],
        )
        size_cat = rng.choice(
            SIZE_CATEGORIES,
            p=[0.25, 0.35, 0.25, 0.15],
        )
        ships.append({
            "mmsi": _random_mmsi(rng, mid),
            "flag": flag,
            "vessel_class": vessel_class,
            "size_category": size_cat,
            "label": 0,
        })

    return pd.DataFrame(ships)


def generate_events(
    ships_df: pd.DataFrame,
    is_shadow: bool,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate AIS turn-off/turn-on events for a set of ships."""
    rng = np.random.default_rng(seed)
    base_time = datetime(2024, 1, 1)
    events = []
    event_id = 0

    for _, ship in ships_df.iterrows():
        if is_shadow:
            n_events = rng.integers(2, 9)  # 2-8 events
        else:
            n_events = rng.integers(1, 5)  # 1-4 events

        for _ in range(n_events):
            event_id += 1

            # Location
            if is_shadow:
                lat, lon = _pick_location_shadow(rng)
            else:
                lat, lon = _pick_location_normal(rng)

            # Speed at turn-off
            if is_shadow:
                speed = max(0, rng.normal(4.5, 2.5))
            else:
                speed = max(0, rng.normal(10.0, 4.0))

            # Distance to nearest AIS station
            if is_shadow:
                nearest_ais = max(5, rng.normal(180, 60))
            else:
                nearest_ais = max(2, rng.normal(50, 40))

            # Unmatched (spoofing indicator)
            if is_shadow:
                unmatched = bool(rng.random() < 0.60)
            else:
                unmatched = bool(rng.random() < 0.10)

            # Turn-off timestamp
            days_offset = rng.integers(0, 365)
            hours_offset = rng.integers(0, 24)
            turn_off = base_time + timedelta(days=int(days_offset), hours=int(hours_offset))

            # Dark duration
            if is_shadow:
                dark_hours = max(0.5, rng.normal(18, 12))
            else:
                dark_hours = max(0.1, rng.normal(2, 3))

            turn_on = turn_off + timedelta(hours=float(dark_hours))

            heading = round(rng.uniform(0, 360), 1)

            events.append({
                "mmsi": ship["mmsi"],
                "event_id": event_id,
                "flag": ship["flag"],
                "nearest_ais_km": round(nearest_ais, 1),
                "unmatched": unmatched,
                "vessel_class": ship["vessel_class"],
                "size_category": ship["size_category"],
                "speed_knots": round(speed, 1),
                "heading": heading,
                "turn_off": turn_off.isoformat(),
                "turn_on": turn_on.isoformat(),
                "lat": lat,
                "lon": lon,
                "label": ship["label"],
            })

    return pd.DataFrame(events)


def main(
    n_shadow: int = 1300,
    n_unlabeled: int = 8000,
    output_dir: str | Path | None = None,
) -> Path:
    """Generate all synthetic data and write to CSV."""
    output_dir = Path(output_dir) if output_dir else DATA_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Generating %d shadow fleet ships...", n_shadow)
    shadow_ships = generate_shadow_fleet_mmsis(n=n_shadow, seed=42)

    logger.info("Generating %d unlabeled ships...", n_unlabeled)
    unlabeled_ships = generate_unlabeled_mmsis(n=n_unlabeled, seed=123)

    logger.info("Generating events for shadow fleet ships...")
    shadow_events = generate_events(shadow_ships, is_shadow=True, seed=42)
    logger.info("  → %d shadow fleet events", len(shadow_events))

    logger.info("Generating events for unlabeled ships...")
    unlabeled_events = generate_events(unlabeled_ships, is_shadow=False, seed=123)
    logger.info("  → %d unlabeled events", len(unlabeled_events))

    all_events = pd.concat([shadow_events, unlabeled_events], ignore_index=True)
    all_events = all_events.sample(frac=1, random_state=42).reset_index(drop=True)

    events_path = output_dir / "synthetic_events.csv"
    all_events.to_csv(events_path, index=False)
    logger.info("Wrote %d events to %s", len(all_events), events_path)

    shadow_path = output_dir / "shadow_fleet_mmsis.csv"
    shadow_ships[["mmsi", "flag", "vessel_class", "label"]].to_csv(shadow_path, index=False)
    logger.info("Wrote %d shadow fleet MMSIs to %s", len(shadow_ships), shadow_path)

    return events_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
    main()
