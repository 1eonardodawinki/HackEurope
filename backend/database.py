"""
Supabase persistence layer — uses httpx to call the PostgREST REST API directly.
This avoids the supabase Python library's broken pyiceberg/pyroaring dependencies
on Python 3.14 / Windows.

All writes are batched and fire-and-forget so they never block the main pipeline.
"""

import os
import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")   # service role key (backend only)

_DB_ENABLED = bool(SUPABASE_URL and SUPABASE_KEY)
_disabled_tables: set[str] = set()   # tables that returned 404 — skip silently after first error

if not _DB_ENABLED:
    print("[DB] Supabase not configured — persistence disabled. Set SUPABASE_URL + SUPABASE_SERVICE_KEY to enable.")


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


async def _insert(table: str, rows: list[dict]) -> None:
    """Fire-and-forget POST to PostgREST."""
    if not _DB_ENABLED or not rows or table in _disabled_tables:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=_headers(), json=rows)
            if resp.status_code == 404:
                _disabled_tables.add(table)
                print(f"[DB] Table '{table}' not found — disabling writes for this session. Create it in Supabase to enable persistence.")
            elif resp.status_code >= 400:
                print(f"[DB] {table} insert error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[DB] {table} request failed: {e}")


async def _upsert(table: str, rows: list[dict], on_conflict: str = "id") -> None:
    """Upsert (insert or update) rows."""
    if not _DB_ENABLED or not rows or table in _disabled_tables:
        return
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_headers(), "Prefer": f"resolution=merge-duplicates,return=minimal"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=rows)
            if resp.status_code == 404:
                _disabled_tables.add(table)
                print(f"[DB] Table '{table}' not found — disabling writes for this session.")
            elif resp.status_code >= 400:
                print(f"[DB] {table} upsert error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[DB] {table} upsert failed: {e}")


async def _select(table: str, params: dict = None) -> list[dict]:
    """GET from PostgREST with query params."""
    if not _DB_ENABLED:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {**_headers(), "Prefer": ""}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers, params=params or {})
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        print(f"[DB] {table} select failed: {e}")
    return []


# ── Ship Positions ────────────────────────────────────────────────────────────

_position_batch: list[dict] = []
_BATCH_SIZE = 40


async def record_ship_positions(ships: list[dict]):
    """Buffer hotzone ship positions; flush when batch is full."""
    global _position_batch

    for ship in ships:
        if not ship.get("in_hotzone"):
            continue
        _position_batch.append({
            "mmsi": ship["mmsi"],
            "name": ship.get("name"),
            "lat": ship["lat"],
            "lon": ship["lon"],
            "sog": ship.get("sog"),
            "cog": ship.get("cog"),
            "ship_type": ship.get("type"),
            "status": ship.get("status", "active"),
            "in_hotzone": ship.get("in_hotzone"),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })

    if len(_position_batch) >= _BATCH_SIZE:
        batch = _position_batch[:]
        _position_batch = []
        asyncio.create_task(_insert("ship_positions", batch))


# ── Incidents ─────────────────────────────────────────────────────────────────

async def save_incident(incident: dict, evaluation: Optional[dict] = None):
    row = {
        "id": incident.get("id"),
        "incident_type": incident.get("type"),
        "mmsi": incident.get("mmsi"),
        "ship_name": incident.get("ship_name"),
        "lat": incident.get("lat"),
        "lon": incident.get("lon"),
        "region": incident.get("region"),
        "severity": incident.get("severity", "medium"),
        "duration_minutes": incident.get("duration_minutes", 0),
        "nearby_ships": json.dumps(incident.get("nearby_ships", [])),
        "occurred_at": incident.get("timestamp", datetime.now(timezone.utc).isoformat()),
    }
    if evaluation:
        row.update({
            "confidence_score": evaluation.get("confidence_score"),
            "ai_incident_type": evaluation.get("incident_type"),
            "commodities_affected": json.dumps(evaluation.get("commodities_affected", [])),
            "evaluator_reasoning": (evaluation.get("reasoning") or "")[:2000],
        })
    await _upsert("incidents", [row])


# ── Intelligence Reports ──────────────────────────────────────────────────────

async def save_report(report: dict):
    meta = report.get("_meta", {})
    row = {
        "region": meta.get("region", "unknown"),
        "title": report.get("title"),
        "executive_summary": report.get("executive_summary"),
        "threat_assessment": report.get("threat_assessment"),
        "incident_pattern": report.get("incident_pattern"),
        "chain_of_thought": (report.get("chain_of_thought") or "")[:5000],
        "overall_confidence": report.get("overall_confidence"),
        "commodity_predictions": json.dumps(report.get("commodity_predictions", [])),
        "supporting_evidence": json.dumps(report.get("supporting_evidence", [])),
        "risk_factors": json.dumps(report.get("risk_factors", [])),
        "incident_count": meta.get("incident_count", 0),
        "critic_rounds": meta.get("critic_rounds", 1),
        "critic_approved": meta.get("final_approved", False),
        "raw_report": json.dumps({k: v for k, v in report.items() if k != "_meta"}),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await _insert("intelligence_reports", [row])
    if _DB_ENABLED:
        print(f"[DB] Saved report for region: {row['region']}")


# ── Zones ─────────────────────────────────────────────────────────────────────

async def load_zones() -> dict:
    """Load all persisted zones. Returns {} if DB is unavailable or table is empty."""
    rows = await _select("zones", {})
    return {
        row["name"]: {
            "min_lat": row["min_lat"],
            "max_lat": row["max_lat"],
            "min_lon": row["min_lon"],
            "max_lon": row["max_lon"],
            "center_lat": row.get("center_lat"),
            "center_lon": row.get("center_lon"),
            "color": row.get("color", "#ff6b00"),
            "description": row.get("description", ""),
            "commodities": row.get("commodities") or [],
        }
        for row in rows
    }


async def save_zone(name: str, zone: dict) -> None:
    await _upsert("zones", [{
        "name": name,
        "min_lat": zone["min_lat"],
        "max_lat": zone["max_lat"],
        "min_lon": zone["min_lon"],
        "max_lon": zone["max_lon"],
        "center_lat": zone.get("center_lat"),
        "center_lon": zone.get("center_lon"),
        "color": zone.get("color", "#ff6b00"),
        "description": zone.get("description", ""),
        "commodities": json.dumps(zone.get("commodities", [])),
    }], on_conflict="name")


async def delete_zone(name: str) -> None:
    if not _DB_ENABLED or "zones" in _disabled_tables:
        return
    url = f"{SUPABASE_URL}/rest/v1/zones"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(url, headers=_headers(), params={"name": f"eq.{name}"})
            if resp.status_code == 404:
                _disabled_tables.add("zones")
            elif resp.status_code >= 400:
                print(f"[DB] zones delete error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[DB] zones delete failed: {e}")


# ── Queries ───────────────────────────────────────────────────────────────────

async def get_recent_incidents(region: str = None, limit: int = 50) -> list[dict]:
    params = {"order": "occurred_at.desc", "limit": str(limit)}
    if region:
        params["region"] = f"eq.{region}"
    return await _select("incidents", params)


async def get_recent_reports(limit: int = 10) -> list[dict]:
    return await _select("intelligence_reports", {
        "select": "id,region,title,overall_confidence,incident_count,critic_approved,created_at",
        "order": "created_at.desc",
        "limit": str(limit),
    })
