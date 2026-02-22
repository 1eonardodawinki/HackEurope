"""
ML Model — dark fleet probability prediction.

Uses the trained PU-Learning model from ml/predict.py with local database data.
Falls back to a conservative default if model or data is unavailable.
"""

import asyncio
import logging
import os
import sqlite3

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(__file__)
HIST_DB_PATH = os.path.join(BASE_DIR, "historical_unmatched.db")
VESSEL_DB_PATH = os.path.join(BASE_DIR, "vessel_data.db")


def _load_vessel_events(mmsi: str) -> pd.DataFrame | None:
    """
    Load detection events for a vessel from local DBs and transform
    into the event schema expected by the ML feature engineering.
    """
    if not os.path.exists(HIST_DB_PATH):
        return None

    conn = sqlite3.connect(HIST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT lat, lon, timestamp, mmsi
            FROM historical_detections
            WHERE CAST(mmsi AS TEXT) = ?
              AND lat IS NOT NULL AND lon IS NOT NULL
            ORDER BY timestamp
            """,
            (str(mmsi),),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    # Load vessel metadata from vessel_data.db
    flag = ""
    vessel_class = "other"
    size_category = "medium"
    if os.path.exists(VESSEL_DB_PATH):
        vconn = sqlite3.connect(VESSEL_DB_PATH)
        vconn.row_factory = sqlite3.Row
        try:
            vrow = vconn.execute(
                """
                SELECT flag, geartype FROM vessel_data
                WHERE CAST(mmsi AS TEXT) = ? LIMIT 1
                """,
                (str(mmsi),),
            ).fetchone()
            if vrow:
                flag = vrow["flag"] or ""
                geartype = (vrow["geartype"] or "").lower()
                if "tanker" in geartype or "oil" in geartype:
                    vessel_class = "tanker"
                elif "cargo" in geartype or "bulk" in geartype or "container" in geartype:
                    vessel_class = "cargo"
                elif "fish" in geartype or "trawl" in geartype:
                    vessel_class = "fishing"
        finally:
            vconn.close()

    # Build events DataFrame from detection points
    events = []
    for i in range(len(rows)):
        r = rows[i]
        ts = r["timestamp"]
        events.append({
            "mmsi": str(mmsi),
            "event_id": i,
            "flag": flag,
            "nearest_ais_km": 50.0,
            "unmatched": True,
            "vessel_class": vessel_class,
            "size_category": size_category,
            "speed_knots": 0.0,
            "heading": 0.0,
            "turn_off": ts,
            "turn_on": ts,
            "lat": float(r["lat"]),
            "lon": float(r["lon"]),
            "label": 0,
        })

    df = pd.DataFrame(events)
    df["turn_off"] = pd.to_datetime(df["turn_off"], utc=True)
    df["turn_on"] = pd.to_datetime(df["turn_on"], utc=True)
    return df


async def get_dark_fleet_probability(mmsi: str, vessel_name: str = "") -> dict:
    """
    Predict the probability that a vessel is operating as part of a shadow/dark fleet.

    Uses the trained PU-Learning model with local detection data.
    """
    try:
        from ml.predict import score_vessel

        events_df = await asyncio.to_thread(_load_vessel_events, mmsi)

        if events_df is not None and not events_df.empty:
            result = score_vessel(mmsi=mmsi, events=events_df, vessel_name=vessel_name)
        else:
            # No local data — try scoring from training data
            result = score_vessel(mmsi=mmsi, vessel_name=vessel_name)

        return result

    except Exception as e:
        logger.warning("ML model scoring failed for MMSI %s: %s", mmsi, e)
        # Conservative fallback — unknown vessel gets low score
        return {
            "mmsi": mmsi,
            "vessel_name": vessel_name,
            "probability": 0.3,
            "risk_tier": "LOW",
            "model_version": "fallback",
            "note": f"Model unavailable: {e}",
        }
