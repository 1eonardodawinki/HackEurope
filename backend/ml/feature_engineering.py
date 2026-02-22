"""
Feature engineering for Shadow Fleet detection.

Transforms raw AIS turn-off/turn-on events into ML-ready features,
then aggregates per ship (MMSI).
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# --- Geographic definitions ---

RUSSIAN_WATERS = [
    {"name": "Black Sea (Russian)", "min_lat": 43.0, "max_lat": 46.5, "min_lon": 36.0, "max_lon": 41.0},
    {"name": "Barents Sea", "min_lat": 68.0, "max_lat": 76.0, "min_lon": 20.0, "max_lon": 55.0},
    {"name": "Far East Russia", "min_lat": 42.0, "max_lat": 55.0, "min_lon": 130.0, "max_lon": 145.0},
]

STS_ZONES = [
    {"name": "Ceuta", "center_lat": 35.89, "center_lon": -5.32, "radius_km": 30},
    {"name": "Kalamata", "center_lat": 36.95, "center_lon": 22.11, "radius_km": 40},
    {"name": "Laconian Gulf", "center_lat": 36.5, "center_lon": 22.8, "radius_km": 30},
    {"name": "Strait of Hormuz", "center_lat": 26.0, "center_lon": 56.5, "radius_km": 100},
]

CONVENIENCE_FLAGS = {
    "Panama", "Liberia", "Marshall Islands", "Cameroon", "Palau",
    "Gabon", "Comoros", "Tanzania", "Togo",
}

# Approximate km per degree at mid-latitudes
KM_PER_DEG = 111.0


def _in_bbox(lat: float, lon: float, bbox: dict) -> bool:
    return (bbox["min_lat"] <= lat <= bbox["max_lat"] and
            bbox["min_lon"] <= lon <= bbox["max_lon"])


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in km using equirectangular projection."""
    dlat = (lat2 - lat1) * KM_PER_DEG
    dlon = (lon2 - lon1) * KM_PER_DEG * np.cos(np.radians((lat1 + lat2) / 2))
    return np.sqrt(dlat**2 + dlon**2)


def compute_event_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute per-event features from raw event data.
    Adds new boolean/numeric columns to the DataFrame.
    """
    df = df.copy()

    # Geographic features
    df["in_russian_waters"] = df.apply(
        lambda r: any(_in_bbox(r["lat"], r["lon"], bbox) for bbox in RUSSIAN_WATERS),
        axis=1,
    )

    df["near_known_sts_zone"] = df.apply(
        lambda r: any(
            _distance_km(r["lat"], r["lon"], z["center_lat"], z["center_lon"]) < z["radius_km"]
            for z in STS_ZONES
        ),
        axis=1,
    )

    # International waters approximation: not in Russian waters and not near major coasts
    # (simplified: far from AIS stations serves as proxy)
    df["in_international_waters"] = (
        ~df["in_russian_waters"] &
        (df["nearest_ais_km"] > 80)
    )

    # STS transfer indicator
    df["likely_sts"] = (
        (df["speed_knots"] < 3.0) &
        (df["in_international_waters"] | df["near_known_sts_zone"])
    )

    # Tracking evasion
    df["far_from_tracking"] = df["nearest_ais_km"] > 100

    # Flag risk
    df["is_convenience_flag"] = df["flag"].isin(CONVENIENCE_FLAGS)

    # Spoofing indicator
    df["is_unmatched"] = df["unmatched"].astype(bool)

    # Dark duration
    df["dark_duration_hours"] = (
        (df["turn_on"] - df["turn_off"]).dt.total_seconds() / 3600
    ).clip(lower=0)

    # Vessel type features
    df["is_tanker"] = df["vessel_class"] == "tanker"
    df["is_large_vessel"] = df["size_category"].isin(["large", "VLCC"])

    # Speed features
    df["is_low_speed"] = df["speed_knots"] < 3.0
    df["is_very_low_speed"] = df["speed_knots"] < 1.0

    logger.info("Computed event-level features for %d events", len(df))
    return df


def aggregate_ship_features(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate event-level features per ship (MMSI).
    Returns one row per unique MMSI with aggregated features.
    """
    agg = events_df.groupby("mmsi").agg(
        count_turnoffs=("event_id", "count"),
        avg_speed_at_turnoff=("speed_knots", "mean"),
        min_speed_at_turnoff=("speed_knots", "min"),
        max_dark_duration_hours=("dark_duration_hours", "max"),
        total_dark_duration_hours=("dark_duration_hours", "sum"),
        avg_dark_duration_hours=("dark_duration_hours", "mean"),
        avg_nearest_ais_km=("nearest_ais_km", "mean"),
        pct_in_russian_waters=("in_russian_waters", "mean"),
        pct_near_sts_zone=("near_known_sts_zone", "mean"),
        pct_unmatched=("is_unmatched", "mean"),
        pct_likely_sts=("likely_sts", "mean"),
        pct_far_from_tracking=("far_from_tracking", "mean"),
        pct_low_speed=("is_low_speed", "mean"),
        is_convenience_flag=("is_convenience_flag", "first"),
        is_tanker=("is_tanker", "first"),
        is_large_vessel=("is_large_vessel", "first"),
        label=("label", "first"),
    ).reset_index()

    # Convert booleans to int for sklearn
    for col in ["is_convenience_flag", "is_tanker", "is_large_vessel"]:
        agg[col] = agg[col].astype(int)

    logger.info(
        "Aggregated features for %d ships (%d positive, %d unlabeled)",
        len(agg),
        (agg["label"] == 1).sum(),
        (agg["label"] == 0).sum(),
    )
    return agg


# Feature columns used by the model (in order)
FEATURE_COLUMNS = [
    "count_turnoffs",
    "avg_speed_at_turnoff",
    "min_speed_at_turnoff",
    "max_dark_duration_hours",
    "total_dark_duration_hours",
    "avg_dark_duration_hours",
    "avg_nearest_ais_km",
    "pct_in_russian_waters",
    "pct_near_sts_zone",
    "pct_unmatched",
    "pct_likely_sts",
    "pct_far_from_tracking",
    "pct_low_speed",
    "is_convenience_flag",
    "is_tanker",
    "is_large_vessel",
]


def engineer_features(events_df: pd.DataFrame) -> pd.DataFrame:
    """
    Full feature engineering pipeline:
    1. Compute event-level features
    2. Aggregate per ship
    Returns one row per MMSI with all features + label.
    """
    logger.info("Starting feature engineering for %d events...", len(events_df))
    events_with_features = compute_event_features(events_df)
    ship_features = aggregate_ship_features(events_with_features)
    return ship_features
