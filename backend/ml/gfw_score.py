"""
GFW (Global Fishing Watch) API integration for shadow fleet ML scoring.

Fetches real vessel data from the GFW API (gap events, encounter events,
vessel identity) and transforms it into the feature format expected by
the ML pipeline, then scores the vessel.

Usage (CLI):
    cd backend
    python -m ml.gfw_score <vessel_id> --token <JWT> [--mmsi <mmsi>] [--name <name>]

Usage (import):
    from ml.gfw_score import score_vessel_from_gfw
    result = score_vessel_from_gfw(
        vessel_id="74a4d6c63-3e59-2914-d8f6-3ca66f637b34",
        token="eyJ..."
    )
"""

import argparse
import json
import logging
from datetime import datetime, timezone

import httpx
import pandas as pd

from .predict import score_vessel

logger = logging.getLogger(__name__)

GFW_BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"

# Scoring window: AFTER training data cutoff (2025-07-31) to avoid data leakage
DEFAULT_START_DATE = "2025-08-01"
DEFAULT_END_DATE = "2026-02-22"


# ── Mapping helpers ───────────────────────────────────────────────────────────

VESSEL_TYPE_MAP = {
    "TANKER":           "tanker",
    "CRUDE_CARRIER":    "tanker",
    "PRODUCT_TANKER":   "tanker",
    "CHEMICAL_TANKER":  "tanker",
    "OIL_TANKER":       "tanker",
    "CARGO":            "cargo",
    "BULK_CARRIER":     "cargo",
    "CONTAINER":        "cargo",
    "FISHING":          "fishing",
    "TRAWLERS":         "fishing",
    "DRIFTING_LONGLINES": "fishing",
}


def _map_vessel_class(gfw_type: str) -> str:
    return VESSEL_TYPE_MAP.get(str(gfw_type).upper(), "other")


def _map_size_category(length_m: float | None) -> str:
    if length_m is None:
        return "medium"
    if length_m >= 250:
        return "VLCC"
    if length_m >= 150:
        return "large"
    if length_m >= 60:
        return "medium"
    return "small"


def _parse_iso(ts: str | None) -> str:
    """Normalize any ISO timestamp string (including Z suffix) to offset-aware."""
    if not ts:
        return datetime.now(timezone.utc).isoformat()
    return ts.replace("Z", "+00:00")


# ── GFW API calls ─────────────────────────────────────────────────────────────

def _get_raw(url: str, headers: dict) -> dict:
    """GET a fully-formed URL (for endpoints needing bracket syntax in params)."""
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_vessel_info(vessel_id: str, headers: dict) -> dict:
    """Fetch vessel identity: flag, vessel class, length."""
    url = f"{GFW_BASE_URL}/vessels/{vessel_id}"
    resp = httpx.get(url, headers=headers, params={"dataset": "public-global-vessel-identity:latest"}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # GFW may return a list under 'entries' or a direct object
    if "entries" in data and data["entries"]:
        entry = data["entries"][0]
    else:
        entry = data

    # Try selfReportedInfo → registeredInfo → combinedSourcesInfo
    info = {}
    for key in ("selfReportedInfo", "registeredInfo", "combinedSourcesInfo"):
        if key in data and data[key]:
            src = data[key]
            if isinstance(src, list):
                src = src[0]
            info = src
            break

    # GFW uses "ssvid" for MMSI
    mmsi = info.get("ssvid", "") or entry.get("ssvid", "") or entry.get("mmsi", "")
    flag = info.get("flag", entry.get("flag", ""))
    # GFW uses "geartypes" / "shiptypes" instead of "vesselType"
    geartypes = info.get("geartypes", [])
    if isinstance(geartypes, list) and geartypes:
        geartype = geartypes[0] if isinstance(geartypes[0], str) else geartypes[0].get("name", "other")
    else:
        geartype = info.get("vesselType", entry.get("vesselType", "other"))
    raw_type = geartype
    length_m = info.get("lengthM") or entry.get("lengthM")

    result = {
        "mmsi": str(mmsi),
        "flag": str(flag),
        "vessel_class": _map_vessel_class(raw_type),
        "size_category": _map_size_category(length_m),
    }
    logger.info(
        "Vessel info → MMSI=%s  flag=%s  class=%s  size=%s",
        result["mmsi"], result["flag"], result["vessel_class"], result["size_category"],
    )
    return result


def fetch_gap_events(
    vessel_id: str, headers: dict,
    start_date: str, end_date: str,
    limit: int = 100,
) -> list[dict]:
    """Fetch AIS gap (turn-off / turn-on) events."""
    url = (
        f"{GFW_BASE_URL}/events?vessels[0]={vessel_id}"
        f"&datasets[0]=public-global-gaps-events:latest"
        f"&start-date={start_date}&end-date={end_date}"
        f"&limit={limit}&offset=0"
    )
    try:
        data = _get_raw(url, headers)
        events = data.get("entries", [])
        logger.info("Gap events fetched: %d", len(events))
        return events
    except httpx.HTTPStatusError as exc:
        logger.warning("Gap events unavailable: %s", exc)
        return []


def fetch_encounter_events(
    vessel_id: str, headers: dict,
    start_date: str, end_date: str,
    limit: int = 100,
) -> list[dict]:
    """Fetch ship-to-ship encounter events (STS proxy)."""
    url = (
        f"{GFW_BASE_URL}/events?vessels[0]={vessel_id}"
        f"&datasets[0]=public-global-encounters-events:latest"
        f"&start-date={start_date}&end-date={end_date}"
        f"&limit={limit}&offset=0"
    )
    try:
        data = _get_raw(url, headers)
        events = data.get("entries", [])
        logger.info("Encounter events fetched: %d", len(events))
        return events
    except httpx.HTTPStatusError as exc:
        logger.warning("Encounter events unavailable: %s", exc)
        return []


# ── Transform GFW → internal event schema ────────────────────────────────────

def _transform_gap_events(gap_events: list[dict], vessel_info: dict) -> list[dict]:
    """
    Map GFW gap events to the internal event schema.

    Internal schema (from data_loader.py):
        mmsi, event_id, flag, nearest_ais_km, unmatched, vessel_class,
        size_category, speed_knots, heading, turn_off, turn_on, lat, lon, label
    """
    rows = []
    for i, ev in enumerate(gap_events):
        # Position from GFW: ev["position"]["lat"/"lon"]
        pos = ev.get("position") or {}
        lat = pos.get("lat", 0.0)
        lon = pos.get("lon", 0.0)

        # Distances from GFW: ev["distances"]["startDistanceFromShoreKm"]
        distances = ev.get("distances") or {}
        nearest_ais_km = distances.get("startDistanceFromShoreKm", 50.0)

        # Gap details from GFW: ev["gap"]
        gap = ev.get("gap") or {}
        unmatched = bool(gap.get("intentionalDisabling", False))
        speed_knots = float(gap.get("impliedSpeedKnots", 0.0) or 0.0)

        rows.append({
            "mmsi":            vessel_info["mmsi"],
            "event_id":        i,
            "flag":            vessel_info["flag"],
            "nearest_ais_km":  float(nearest_ais_km),
            "unmatched":       unmatched,
            "vessel_class":    vessel_info["vessel_class"],
            "size_category":   vessel_info["size_category"],
            "speed_knots":     speed_knots,
            "heading":         0.0,
            "turn_off":        _parse_iso(ev.get("start")),
            "turn_on":         _parse_iso(ev.get("end")),
            "lat":             float(lat),
            "lon":             float(lon),
            "label":           0,
        })
    return rows


def _transform_encounter_events(
    encounter_events: list[dict],
    vessel_info: dict,
    id_offset: int = 1000,
) -> list[dict]:
    """
    Map GFW encounter events to internal event format.
    Encounters in open water are a strong STS transfer signal.
    """
    rows = []
    for i, ev in enumerate(encounter_events):
        pos = ev.get("position") or {}
        lat = pos.get("lat", 0.0)
        lon = pos.get("lon", 0.0)

        distances = ev.get("distances") or {}
        nearest_ais_km = distances.get("startDistanceFromShoreKm", 60.0)

        encounter = ev.get("encounter") or {}
        speed_knots = float(encounter.get("medianSpeedKnots", 1.0) or 1.0)

        rows.append({
            "mmsi":            vessel_info["mmsi"],
            "event_id":        id_offset + i,
            "flag":            vessel_info["flag"],
            "nearest_ais_km":  float(nearest_ais_km),
            "unmatched":       False,
            "vessel_class":    vessel_info["vessel_class"],
            "size_category":   vessel_info["size_category"],
            "speed_knots":     speed_knots,
            "heading":         0.0,
            "turn_off":        _parse_iso(ev.get("start")),
            "turn_on":         _parse_iso(ev.get("end")),
            "lat":             float(lat),
            "lon":             float(lon),
            "label":           0,
        })
    return rows


# ── Main scoring function ─────────────────────────────────────────────────────

def score_vessel_from_gfw(
    vessel_id: str,
    token: str,
    mmsi: str = "",
    vessel_name: str = "",
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
) -> dict:
    """
    Full pipeline: GFW API fetch → transform → ML score.

    Parameters
    ----------
    vessel_id   : GFW vessel ID (e.g. "74a4d6c63-3e59-2914-d8f6-3ca66f637b34")
    token       : GFW API JWT bearer token
    mmsi        : MMSI override (if not in GFW response)
    vessel_name : Optional display name
    start_date  : Event fetch start (YYYY-MM-DD)
    end_date    : Event fetch end   (YYYY-MM-DD)

    Returns
    -------
    dict with: mmsi, vessel_name, probability, risk_tier,
               model_version, feature_contributions, gfw_summary
    """
    headers = {"Authorization": f"Bearer {token}"}

    logger.info("Fetching GFW data for vessel_id=%s", vessel_id)

    # 1. Vessel identity
    vessel_info = fetch_vessel_info(vessel_id, headers)
    if mmsi:
        vessel_info["mmsi"] = mmsi  # allow caller override

    # 2. Gap events (AIS dark periods)
    gap_events = fetch_gap_events(vessel_id, headers, start_date, end_date)

    # 3. Encounter events (STS transfers)
    encounter_events = fetch_encounter_events(vessel_id, headers, start_date, end_date)

    # 4. Transform to internal schema
    rows = _transform_gap_events(gap_events, vessel_info)
    rows += _transform_encounter_events(encounter_events, vessel_info, id_offset=1000)

    if not rows:
        logger.warning("No events found for vessel %s — returning default score", vessel_id)
        return {
            "mmsi":                 vessel_info["mmsi"],
            "vessel_name":          vessel_name,
            "probability":          0.5,
            "risk_tier":            "MEDIUM",
            "model_version":        "unknown",
            "feature_contributions": {},
            "gfw_summary": {
                "vessel_id":              vessel_id,
                "gap_events_count":       0,
                "encounter_events_count": 0,
                "flag":                   vessel_info["flag"],
                "vessel_class":           vessel_info["vessel_class"],
            },
            "note": "No GFW events found in date range — defaulting to MEDIUM",
        }

    # 5. Parse timestamps
    events_df = pd.DataFrame(rows)
    events_df["turn_off"] = pd.to_datetime(events_df["turn_off"], utc=True)
    events_df["turn_on"]  = pd.to_datetime(events_df["turn_on"],  utc=True)

    logger.info(
        "Scoring %s with %d events (%d gap, %d encounter)",
        vessel_info["mmsi"], len(rows), len(gap_events), len(encounter_events),
    )

    # 6. ML score
    result = score_vessel(
        mmsi=vessel_info["mmsi"],
        events=events_df,
        vessel_name=vessel_name,
    )

    # 7. Attach GFW metadata
    result["gfw_summary"] = {
        "vessel_id":              vessel_id,
        "gap_events_count":       len(gap_events),
        "encounter_events_count": len(encounter_events),
        "flag":                   vessel_info["flag"],
        "vessel_class":           vessel_info["vessel_class"],
        "size_category":          vessel_info["size_category"],
        "date_range":             f"{start_date} → {end_date}",
    }

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Score a vessel via GFW API + Shadow Fleet ML model"
    )
    parser.add_argument("vessel_id", help="GFW vessel ID")
    parser.add_argument("--token",  required=True, help="GFW API bearer token")
    parser.add_argument("--mmsi",   default="",    help="MMSI override")
    parser.add_argument("--name",   default="",    help="Vessel name")
    parser.add_argument("--start",  default=DEFAULT_START_DATE, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end",    default=DEFAULT_END_DATE,   help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    result = score_vessel_from_gfw(
        vessel_id=args.vessel_id,
        token=args.token,
        mmsi=args.mmsi,
        vessel_name=args.name,
        start_date=args.start,
        end_date=args.end,
    )

    gfw = result.get("gfw_summary", {})

    print("\n" + "=" * 60)
    print("  SHADOW FLEET ML SCORE — REAL GFW DATA")
    print("=" * 60)
    print(f"  MMSI:         {result['mmsi']}")
    print(f"  Vessel:       {result.get('vessel_name') or '—'}")
    print(f"  Probability:  {result['probability']:.1%}")
    print(f"  Risk Tier:    {result['risk_tier']}")
    print(f"  Model:        {result.get('model_version', '—')}")
    print(f"\n  GFW Data:")
    print(f"    Flag:       {gfw.get('flag', '—')}")
    print(f"    Class:      {gfw.get('vessel_class', '—')}")
    print(f"    Gap events: {gfw.get('gap_events_count', 0)}")
    print(f"    Encounters: {gfw.get('encounter_events_count', 0)}")
    print(f"    Date range: {gfw.get('date_range', '—')}")

    contribs = result.get("feature_contributions", {})
    if contribs:
        print(f"\n  Top Feature Contributions:")
        for feat, vals in contribs.items():
            print(f"    {feat:<35} importance={vals['importance']:.4f}  value={vals['value']:.4f}")

    if "note" in result:
        print(f"\n  Note: {result['note']}")

    print("\n  Full JSON:")
    print(json.dumps(result, indent=2, default=str))
    print("=" * 60)


if __name__ == "__main__":
    main()
