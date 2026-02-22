"""
Local MMSI intelligence context from project SQLite files.

Sources:
- backend/vessel_data.db (table: vessel_data)
- backend/historical_unmatched.db (table: historical_detections)
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

BASE_DIR = os.path.dirname(__file__)
VESSEL_DB_PATH = os.path.join(BASE_DIR, "vessel_data.db")
HIST_DB_PATH = os.path.join(BASE_DIR, "historical_unmatched.db")


def _as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _safe_distinct(rows: list[sqlite3.Row], key: str, limit: int = 5) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        v = _as_text(row[key])
        if not v or v in seen:
            continue
        seen.add(v)
        out.append(v)
        if len(out) >= limit:
            break
    return out


def _load_vessel_profile(mmsi: str) -> dict[str, Any]:
    if not os.path.exists(VESSEL_DB_PATH):
        return {"available": False, "error": "vessel_data.db not found"}

    conn = sqlite3.connect(VESSEL_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT vessel_record_id, shipname, n_shipname, n_callsign, imo, flag,
                   owner, owner_flag, geartype, source_code, first_timestamp, last_timestamp
            FROM vessel_data
            WHERE CAST(mmsi AS TEXT) = ?
            """,
            (mmsi,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"available": True, "record_count": 0}

    return {
        "available": True,
        "record_count": len(rows),
        "ship_names": _safe_distinct(rows, "shipname"),
        "normalized_names": _safe_distinct(rows, "n_shipname"),
        "flags": _safe_distinct(rows, "flag"),
        "owners": _safe_distinct(rows, "owner"),
        "owner_flags": _safe_distinct(rows, "owner_flag"),
        "callsigns": _safe_distinct(rows, "n_callsign"),
        "imos": _safe_distinct(rows, "imo"),
        "gear_types": _safe_distinct(rows, "geartype"),
        "source_codes": _safe_distinct(rows, "source_code"),
        "first_seen": min((_as_text(r["first_timestamp"]) for r in rows if _as_text(r["first_timestamp"])), default=""),
        "last_seen": max((_as_text(r["last_timestamp"]) for r in rows if _as_text(r["last_timestamp"])), default=""),
    }


def _load_unmatched_history(mmsi: str) -> dict[str, Any]:
    if not os.path.exists(HIST_DB_PATH):
        return {"available": False, "error": "historical_unmatched.db not found"}

    conn = sqlite3.connect(HIST_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        stats = conn.execute(
            """
            SELECT COUNT(*) AS point_count,
                   MIN(timestamp) AS first_seen,
                   MAX(timestamp) AS last_seen,
                   AVG(lat) AS avg_lat,
                   AVG(lon) AS avg_lon
            FROM historical_detections
            WHERE CAST(mmsi AS TEXT) = ?
              AND lat IS NOT NULL
              AND lon IS NOT NULL
            """,
            (mmsi,),
        ).fetchone()

        sample_rows = conn.execute(
            """
            SELECT lat, lon, timestamp
            FROM historical_detections
            WHERE CAST(mmsi AS TEXT) = ?
              AND lat IS NOT NULL
              AND lon IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 5
            """,
            (mmsi,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "available": True,
        "point_count": int(stats["point_count"] or 0),
        "first_seen": _as_text(stats["first_seen"]),
        "last_seen": _as_text(stats["last_seen"]),
        "centroid": {
            "lat": float(stats["avg_lat"]) if stats["avg_lat"] is not None else None,
            "lon": float(stats["avg_lon"]) if stats["avg_lon"] is not None else None,
        },
        "sample_points": [
            {"lat": float(r["lat"]), "lon": float(r["lon"]), "timestamp": _as_text(r["timestamp"])}
            for r in sample_rows
        ],
    }


def load_mmsi_context(mmsi: str) -> dict[str, Any]:
    """Load local vessel identity + unmatched history context for one MMSI."""
    mmsi = _as_text(mmsi)
    return {
        "mmsi": mmsi,
        "vessel_data": _load_vessel_profile(mmsi),
        "historical_unmatched": _load_unmatched_history(mmsi),
    }
