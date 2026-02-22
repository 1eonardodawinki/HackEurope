"""
Load real training data from the project's SQLite databases.

Sources:
  - backend/vessel_data.db       → vessel identity (flag, geartype, length, owner)
  - backend/historical_unmatched.db → satellite detections with no AIS match (= went dark)
  - backend/Flagged vessels.csv  → confirmed illegal vessel IMOs (label=1)

Labeling strategy (hybrid PU Learning):
  - label=1 if IMO is in the confirmed flagged vessels list, OR
  - label=1 if vessel has strong heuristic signals (many detections + convenience flag
    + near suspicious zone + tanker/carrier)
  - label=0 for everything else (unlabeled, not necessarily clean)

Usage:
    cd backend
    python -m ml.load_real_data          # writes ml/data/real_events.csv
    python -m ml.run_pipeline --step train   # train on the new data
"""

import csv
import io
import logging
import os
import sqlite3
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
BACKEND_DIR = Path(__file__).parent.parent  # backend/

VESSEL_DB = BACKEND_DIR / "vessel_data.db"
HIST_DB = BACKEND_DIR / "historical_unmatched.db"
FLAGGED_CSV = BACKEND_DIR / "Flagged vessels.csv"
OPENSANCTIONS_CSV = DATA_DIR / "opensanctions_maritime.csv"
OPENSANCTIONS_URL = "https://data.opensanctions.org/datasets/20260221/maritime/maritime.csv"

# Temporal split: training data cutoff to prevent data leakage with API scoring
TRAIN_CUTOFF_DATE = "2025-07-31 23:59:59"

# ── Convenience flags (same as feature_engineering.py) ────────────────────────

CONVENIENCE_FLAGS = {
    "PAN", "LBR", "MHL", "CMR", "PLW", "GAB", "COM", "TZA", "TGO",
    # Also add 3-letter codes used in vessel_data
    "Panama", "Liberia", "Marshall Islands", "Cameroon", "Palau",
    "Gabon", "Comoros", "Tanzania", "Togo",
}

# ── Sanctioned / suspicious zones for labeling ───────────────────────────────

RUSSIAN_OIL_PORTS = [
    {"name": "Novorossiysk", "lat": 44.7167, "lon": 37.7833, "radius_km": 30},
    {"name": "Primorsk",     "lat": 60.3667, "lon": 28.6333, "radius_km": 30},
    {"name": "Ust-Luga",     "lat": 59.6833, "lon": 28.4000, "radius_km": 30},
    {"name": "Kozmino",      "lat": 42.7833, "lon": 133.0500, "radius_km": 30},
    {"name": "Murmansk",     "lat": 68.9667, "lon": 33.0500, "radius_km": 30},
]

IRANIAN_PORTS = [
    {"name": "Kharg Island",         "lat": 29.2333, "lon": 50.3167, "radius_km": 30},
    {"name": "Bandar Abbas",         "lat": 27.1833, "lon": 56.2833, "radius_km": 30},
    {"name": "Bandar Imam Khomeini", "lat": 30.4333, "lon": 49.0667, "radius_km": 30},
]

STS_ZONES = [
    {"name": "Ceuta",       "lat": 35.89,  "lon": -5.30,   "radius_km": 50},
    {"name": "Kalamata",    "lat": 36.95,  "lon": 22.11,   "radius_km": 50},
    {"name": "Laconia",     "lat": 36.50,  "lon": 22.90,   "radius_km": 50},
    {"name": "Fujairah",    "lat": 25.12,  "lon": 56.33,   "radius_km": 50},
    {"name": "Lomé",        "lat": 6.133,  "lon": 1.25,    "radius_km": 50},
    {"name": "South Africa","lat": -34.00, "lon": 18.00,   "radius_km": 100},
    {"name": "Singapore",   "lat": 1.20,   "lon": 103.80,  "radius_km": 50},
    {"name": "Malaysia",    "lat": 1.30,   "lon": 104.10,  "radius_km": 50},
]

KM_PER_DEG = 111.0


def _distance_km(lat1, lon1, lat2, lon2):
    dlat = (lat2 - lat1) * KM_PER_DEG
    dlon = (lon2 - lon1) * KM_PER_DEG * np.cos(np.radians((lat1 + lat2) / 2))
    return np.sqrt(dlat**2 + dlon**2)


def _near_any_zone(lat, lon, zones):
    for z in zones:
        if _distance_km(lat, lon, z["lat"], z["lon"]) < z["radius_km"]:
            return True
    return False


# ── Geartype → vessel_class mapping ──────────────────────────────────────────

def _map_geartype(geartype: str) -> str:
    if not geartype:
        return "other"
    g = geartype.lower()
    if "tanker" in g or "oil" in g:
        return "tanker"
    if "cargo" in g or "bulk" in g or "container" in g or "carrier" in g or "reefer" in g or "bunker" in g:
        return "cargo"
    if "fish" in g or "trawl" in g or "longline" in g or "purse" in g or "jigger" in g or "gillnet" in g:
        return "fishing"
    return "other"


def _map_size(length_m) -> str:
    if length_m is None or length_m == "":
        return "medium"
    try:
        l = float(length_m)
    except (ValueError, TypeError):
        return "medium"
    if l >= 250:
        return "VLCC"
    if l >= 150:
        return "large"
    if l >= 60:
        return "medium"
    return "small"


# ── Main loading function ─────────────────────────────────────────────────────

def _load_opensanctions_imos() -> set[str]:
    """Load sanctioned/shadow-fleet IMOs from the OpenSanctions maritime CSV."""
    if not OPENSANCTIONS_CSV.exists():
        # Try downloading
        try:
            import httpx
            logger.info("Downloading OpenSanctions maritime data...")
            resp = httpx.get(OPENSANCTIONS_URL, follow_redirects=True, timeout=60)
            if resp.status_code == 200:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                OPENSANCTIONS_CSV.write_text(resp.text)
                logger.info("Saved OpenSanctions CSV (%d bytes)", len(resp.text))
            else:
                logger.warning("Failed to download OpenSanctions: %d", resp.status_code)
                return set()
        except Exception as e:
            logger.warning("Could not download OpenSanctions: %s", e)
            return set()

    sanctioned_imos: set[str] = set()
    with open(OPENSANCTIONS_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            risk = row.get("risk", "")
            # Only take vessels that are sanctioned or shadow-fleet tagged
            if "sanction" in risk or "mare.shadow" in risk:
                imo_raw = row.get("imo", "").strip()
                if imo_raw.startswith("IMO"):
                    sanctioned_imos.add(imo_raw.replace("IMO", "").strip())
    logger.info("Loaded %d sanctioned/shadow IMOs from OpenSanctions", len(sanctioned_imos))
    return sanctioned_imos


def _load_flagged_imos() -> set[str]:
    """Load all flagged IMOs from user CSV + OpenSanctions."""
    imos: set[str] = set()

    # Source 1: User's flagged vessels CSV
    if FLAGGED_CSV.exists():
        df = pd.read_csv(FLAGGED_CSV)
        col = df.columns[0]  # header is "sanctuald MMSI" but values are IMOs
        user_imos = set(df[col].dropna().astype(str).str.strip())
        imos.update(user_imos)
        logger.info("Loaded %d flagged IMOs from %s", len(user_imos), FLAGGED_CSV.name)
    else:
        logger.warning("Flagged vessels CSV not found at %s", FLAGGED_CSV)

    # Source 2: OpenSanctions (EU/US/UN sanctions + shadow fleet)
    os_imos = _load_opensanctions_imos()
    imos.update(os_imos)

    logger.info("Total unique flagged IMOs (union): %d", len(imos))
    return imos


def load_real_data(
    min_detections_positive: int = 5,
    max_events_per_vessel: int = 50,
) -> pd.DataFrame:
    """
    Load real data from SQLite databases and produce a DataFrame
    in the same schema as the synthetic data.

    Labeling strategy (hybrid PU Learning):
      label=1 (confirmed): vessel IMO is in the flagged vessels list
      label=1 (heuristic): vessels with ≥min_detections_positive unmatched
              detections AND at least one suspicious signal
      label=0 (unlabeled): everything else
    """
    if not VESSEL_DB.exists():
        raise FileNotFoundError(f"vessel_data.db not found at {VESSEL_DB}")
    if not HIST_DB.exists():
        raise FileNotFoundError(f"historical_unmatched.db not found at {HIST_DB}")

    # ── 0. Load confirmed flagged IMOs ───────────────────────────────────
    flagged_imos = _load_flagged_imos()

    # ── 1. Load vessel identity (now including IMO for matching) ─────────
    logger.info("Loading vessel_data.db...")
    vconn = sqlite3.connect(str(VESSEL_DB))
    vessel_df = pd.read_sql_query(
        """
        SELECT DISTINCT
            CAST(mmsi AS TEXT) AS mmsi,
            CAST(imo AS TEXT) AS imo,
            flag,
            geartype,
            length_m,
            is_carrier,
            is_bunker,
            owner_flag
        FROM vessel_data
        WHERE mmsi IS NOT NULL AND mmsi != ''
        """,
        vconn,
    )
    vconn.close()

    # Deduplicate: keep first row per MMSI
    vessel_df = vessel_df.drop_duplicates(subset="mmsi", keep="first")
    logger.info("Loaded %d unique vessels from vessel_data.db", len(vessel_df))

    # Mark MMSIs whose IMO is in the flagged list
    vessel_df["imo_clean"] = vessel_df["imo"].fillna("").astype(str).str.strip()
    flagged_mmsis = set(
        vessel_df[vessel_df["imo_clean"].isin(flagged_imos)]["mmsi"].tolist()
    )
    logger.info(
        "Flagged IMOs matched → %d MMSIs confirmed positive",
        len(flagged_mmsis),
    )

    # ── 2. Load historical detections ─────────────────────────────────────
    logger.info("Loading historical_unmatched.db...")
    hconn = sqlite3.connect(str(HIST_DB))
    hist_df = pd.read_sql_query(
        """
        SELECT
            CAST(mmsi AS TEXT) AS mmsi,
            timestamp,
            lat,
            lon,
            matching_score,
            length_m AS det_length_m
        FROM historical_detections
        WHERE mmsi IS NOT NULL
          AND mmsi != ''
          AND mmsi != '0'
          AND mmsi != '999999999'
          AND mmsi != '123456789'
          AND mmsi != '200000000'
          AND lat IS NOT NULL
          AND lon IS NOT NULL
          AND timestamp <= ?
        """,
        hconn,
        params=(TRAIN_CUTOFF_DATE,),
    )
    hconn.close()
    logger.info("Loaded %d detection rows for %d unique MMSIs (cutoff: %s)",
                len(hist_df), hist_df["mmsi"].nunique(), TRAIN_CUTOFF_DATE)

    # ── 3. Join detections with vessel identity ───────────────────────────
    merged = hist_df.merge(vessel_df, on="mmsi", how="left")
    merged["flag"] = merged["flag"].fillna("")
    merged["geartype"] = merged["geartype"].fillna("")
    merged["length_m"] = merged["length_m"].fillna(merged["det_length_m"])
    merged["is_carrier"] = merged["is_carrier"].fillna("")
    merged["is_bunker"] = merged["is_bunker"].fillna("")

    # ── 4. Compute per-MMSI stats for labeling ───────────────────────────
    mmsi_stats = merged.groupby("mmsi").agg(
        detection_count=("lat", "count"),
        avg_lat=("lat", "mean"),
        avg_lon=("lon", "mean"),
        flag=("flag", "first"),
        geartype=("geartype", "first"),
        is_carrier=("is_carrier", "first"),
        is_bunker=("is_bunker", "first"),
    ).reset_index()

    # Suspicious signals
    mmsi_stats["is_convenience_flag"] = mmsi_stats["flag"].str.upper().isin(CONVENIENCE_FLAGS)
    mmsi_stats["vessel_class"] = mmsi_stats["geartype"].apply(_map_geartype)
    mmsi_stats["is_tanker_or_carrier"] = (
        (mmsi_stats["vessel_class"] == "tanker") |
        (mmsi_stats["vessel_class"] == "cargo") |
        (mmsi_stats["is_carrier"].str.lower() == "true") |
        (mmsi_stats["is_bunker"].str.lower() == "true")
    )
    mmsi_stats["near_suspicious_zone"] = mmsi_stats.apply(
        lambda r: (
            _near_any_zone(r["avg_lat"], r["avg_lon"], RUSSIAN_OIL_PORTS) or
            _near_any_zone(r["avg_lat"], r["avg_lon"], IRANIAN_PORTS) or
            _near_any_zone(r["avg_lat"], r["avg_lon"], STS_ZONES)
        ),
        axis=1,
    )

    # ── Hybrid PU labeling ─────────────────────────────────────────────
    mmsi_stats["label"] = 0

    # Source 1: Confirmed flagged vessels (IMO match)
    confirmed_mask = mmsi_stats["mmsi"].isin(flagged_mmsis)
    mmsi_stats.loc[confirmed_mask, "label"] = 1
    n_confirmed = confirmed_mask.sum()

    # Source 2: Heuristic positives (strong suspicious signals)
    heuristic_mask = (
        (mmsi_stats["label"] == 0) &  # only those not already confirmed
        (mmsi_stats["detection_count"] >= min_detections_positive) &
        (
            mmsi_stats["is_convenience_flag"] |
            mmsi_stats["near_suspicious_zone"] |
            mmsi_stats["is_tanker_or_carrier"]
        )
    )
    mmsi_stats.loc[heuristic_mask, "label"] = 1
    n_heuristic = heuristic_mask.sum()

    n_positive = (mmsi_stats["label"] == 1).sum()
    n_unlabeled = (mmsi_stats["label"] == 0).sum()
    logger.info(
        "Labeling: %d positive (%d confirmed + %d heuristic), %d unlabeled",
        n_positive, n_confirmed, n_heuristic, n_unlabeled,
    )

    # ── 5. Build event rows in internal schema ────────────────────────────
    label_map = mmsi_stats.set_index("mmsi")["label"].to_dict()
    vessel_class_map = mmsi_stats.set_index("mmsi")["vessel_class"].to_dict()

    events = []
    event_id = 0

    for mmsi, group in merged.groupby("mmsi"):
        group = group.head(max_events_per_vessel)  # cap events per vessel

        for _, row in group.iterrows():
            event_id += 1

            # Parse timestamp
            ts = row["timestamp"]

            # nearest_ais_km: use matching_score as inverse proxy
            # matching_score close to 0 = no AIS match = far from AIS
            matching = row.get("matching_score") or 0.0
            try:
                matching = float(matching)
            except (ValueError, TypeError):
                matching = 0.0
            # Transform: low matching_score → high distance
            nearest_ais_km = max(5.0, (1.0 - matching) * 200.0)

            # Dark duration estimate: unknown, use 6h default for unmatched
            dark_hours = 6.0

            events.append({
                "mmsi":           str(mmsi),
                "event_id":       event_id,
                "flag":           str(row["flag"] or ""),
                "nearest_ais_km": round(nearest_ais_km, 1),
                "unmatched":      True,  # all detections are unmatched
                "vessel_class":   vessel_class_map.get(mmsi, "other"),
                "size_category":  _map_size(row["length_m"]),
                "speed_knots":    0.0,  # not available from satellite detections
                "heading":        0.0,
                "turn_off":       ts,
                "turn_on":        ts,  # will be offset in post-processing
                "lat":            float(row["lat"]),
                "lon":            float(row["lon"]),
                "label":          label_map.get(mmsi, 0),
            })

    events_df = pd.DataFrame(events)

    # Post-process: add dark duration to turn_on
    events_df["turn_off"] = pd.to_datetime(events_df["turn_off"], format="mixed", utc=True)
    events_df["turn_on"] = events_df["turn_off"] + timedelta(hours=6)

    logger.info(
        "Built %d events for %d vessels (%d positive, %d unlabeled)",
        len(events_df), events_df["mmsi"].nunique(),
        events_df[events_df["label"] == 1]["mmsi"].nunique(),
        events_df[events_df["label"] == 0]["mmsi"].nunique(),
    )

    return events_df


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    events_df = load_real_data()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "real_events.csv"
    events_df.to_csv(out_path, index=False)
    logger.info("Saved %d events to %s", len(events_df), out_path)

    # Also save the positive MMSI list
    positive_mmsis = events_df[events_df["label"] == 1]["mmsi"].unique()
    shadow_path = DATA_DIR / "real_shadow_fleet_mmsis.csv"
    pd.DataFrame({"mmsi": positive_mmsis}).to_csv(shadow_path, index=False)
    logger.info("Saved %d positive MMSIs to %s", len(positive_mmsis), shadow_path)

    print(f"\nDone: {len(events_df)} events, {len(positive_mmsis)} positive MMSIs")
    print(f"Now run: python -m ml.run_pipeline --step train")


if __name__ == "__main__":
    main()
