"""
GFW Track Microservice  —  port 8001
Standalone service: does NOT touch the main app codebase.

How it works:
  1. Resolve MMSI → GFW vessel_id  (one /vessels/search call)
  2. Fetch port-visit events for that vessel  (one /events call per dataset)
  3. Sort by timestamp, return clean JSON path

Endpoint:
  GET /track?mmsi=229594000
  GET /track?mmsi=229594000&start=2025-01-01&end=2025-06-01

CORS is wide-open so the frontend can call it directly at http://localhost:8001.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

GFW_TOKEN = os.getenv("GFW_API_TOKEN", "")
BASE_URL   = "https://gateway.api.globalfishingwatch.org/v3"
HEADERS    = {
    "Authorization": f"Bearer {GFW_TOKEN}",
    "Content-Type":  "application/json",
}

EVENT_DATASETS = [
    "public-global-port-visits-events:latest",
    "public-global-fishing-events:latest",
    "public-global-encounters-events:latest",
]


# ── Pydantic models ──────────────────────────────────────────────────────────

class TrackPoint(BaseModel):
    lat: float
    lon: float
    timestamp: str   # ISO date/datetime string


class TrackResponse(BaseModel):
    mmsi: str
    name: str
    flag: str
    ship_type: str
    time_range: str
    point_count: int
    points: List[TrackPoint]


# ── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(title="GFW Track Service", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ── GFW helpers ──────────────────────────────────────────────────────────────

def _find_vessel(mmsi: str) -> tuple:
    """Return (vessel_id, {name, flag, ship_type}) for a given MMSI."""
    with httpx.Client(timeout=20) as client:
        r = client.get(
            f"{BASE_URL}/vessels/search",
            params={
                "query":        mmsi,
                "datasets[0]":  "public-global-vessel-identity:latest",
                "limit":        5,
            },
            headers=HEADERS,
        )

    if r.status_code != 200:
        raise HTTPException(502, f"GFW vessel search failed: {r.status_code}")

    entries = r.json().get("entries", [])
    if not entries:
        raise HTTPException(404, f"Vessel MMSI {mmsi} not found in GFW")

    entry = entries[0]
    vessel_id = name = flag = ship_type = None

    for info in entry.get("selfReportedInfo") or []:
        if not vessel_id:
            vessel_id = info.get("id")
        if str(info.get("ssvid", "")) == str(mmsi):
            vessel_id = info.get("id") or vessel_id
            name = info.get("shipname") or info.get("nShipname") or name
            flag = info.get("flag") or flag

    if not vessel_id:
        cs = (entry.get("combinedSourcesInfo") or [{}])[0]
        vessel_id = cs.get("vesselId")
        for st in cs.get("shiptypes") or []:
            ship_type = st.get("name", ship_type)

    reg = (entry.get("registryInfo") or [{}])[0]
    return vessel_id, {
        "name":      name      or reg.get("shipname") or reg.get("nShipname") or "Unknown",
        "flag":      flag      or reg.get("flag")     or "?",
        "ship_type": ship_type or reg.get("geartype") or "Unknown",
    }


def _fetch_events(vessel_id: str, start: str, end: str) -> list:
    """
    Fetch all event positions for one vessel from GFW Events API.
    Queries port-visits, fishing, and encounter datasets.
    Each call is for ONE vessel only — no regional filtering needed.
    """
    points = []

    with httpx.Client(timeout=30) as client:
        for dataset in EVENT_DATASETS:
            offset = 0
            while True:
                r = client.get(
                    f"{BASE_URL}/events",
                    params={
                        "datasets[0]":  dataset,
                        "vessels[0]":   vessel_id,
                        "start-date":   start,
                        "end-date":     end,
                        "limit":        200,
                        "offset":       offset,
                    },
                    headers=HEADERS,
                    timeout=30,
                )
                if r.status_code != 200:
                    break

                entries = r.json().get("entries", [])
                if not entries:
                    break

                for e in entries:
                    lat = lon = ts = None

                    pos = e.get("position") or {}
                    lat = pos.get("lat") or pos.get("latitude")
                    lon = pos.get("lon") or pos.get("longitude")

                    if lat is None or lon is None:
                        bbox = e.get("boundingBox") or e.get("bounding_box")
                        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                            lon = (float(bbox[0]) + float(bbox[2])) / 2
                            lat = (float(bbox[1]) + float(bbox[3])) / 2

                    if lat is None or lon is None:
                        continue

                    lat, lon = float(lat), float(lon)
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        continue

                    ts = e.get("start") or e.get("startDate") or e.get("timestamp") or ""
                    points.append({"lat": lat, "lon": lon, "timestamp": str(ts)})

                if len(entries) < 200:
                    break
                offset += 200

    return points


def _densify_segment(coords: list, steps: int = 8) -> list:
    """Add intermediate interpolated points between each pair of waypoints."""
    if len(coords) < 2:
        return coords
    out = []
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i + 1]
        out.append([lon1, lat1])
        for s in range(1, steps):
            t = s / steps
            out.append([lon1 + t * (lon2 - lon1), lat1 + t * (lat2 - lat1)])
    out.append(coords[-1])
    return out


def _apply_maritime_routing(points: list) -> list:
    """
    Replace straight lines between event positions with actual maritime routes.
    Uses searoute (offline, pre-computed shipping graph) so lines follow navigable
    waterways. Each leg is then densified with intermediate interpolation so
    Mapbox renders smooth curves rather than straight lines that may clip land.
    Falls back to densified direct interpolation if routing fails for any leg.
    """
    try:
        import searoute as sr
    except ImportError:
        return points

    if len(points) < 2:
        return points

    out = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        try:
            route = sr.searoute([a["lon"], a["lat"]], [b["lon"], b["lat"]])
            raw_coords = route["geometry"]["coordinates"]  # [[lon, lat], ...]
            dense = _densify_segment(raw_coords, steps=20)
            for lon, lat in dense[:-1]:
                out.append({"lat": lat, "lon": lon, "timestamp": a["timestamp"]})
        except Exception:
            # Fallback: simple interpolation so we at least avoid a 1-segment straight line
            fallback = _densify_segment([[a["lon"], a["lat"]], [b["lon"], b["lat"]]], steps=20)
            for lon, lat in fallback[:-1]:
                out.append({"lat": lat, "lon": lon, "timestamp": a["timestamp"]})
    out.append(points[-1])
    return out


def _sort_and_dedupe(points: list) -> list:
    """Sort by timestamp, remove duplicates."""
    def _ts_sort_key(p):
        ts = p.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        except Exception:
            return ts

    points.sort(key=_ts_sort_key)

    seen = set()
    out = []
    for p in points:
        key = (round(p["lat"], 2), round(p["lon"], 2))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/track", response_model=TrackResponse)
async def get_track(
    mmsi: str = Query(..., description="9-digit vessel MMSI"),
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Return the port-visit / event-based track for one vessel.
    Queries GFW Events API with a direct vessel_id filter — no regional scan.
    """
    if not GFW_TOKEN:
        raise HTTPException(503, "GFW_API_TOKEN not set in .env")

    today = datetime.now(timezone.utc)
    start = start or (today - timedelta(days=365)).strftime("%Y-%m-%d")
    end   = end   or today.strftime("%Y-%m-%d")

    # 1. Resolve vessel_id
    import asyncio
    vessel_id, identity = await asyncio.to_thread(_find_vessel, mmsi.strip())

    if not vessel_id:
        raise HTTPException(404, f"No GFW vessel_id found for MMSI {mmsi}")

    # 2. Fetch events for this ONE vessel
    points_raw = await asyncio.to_thread(_fetch_events, vessel_id, start, end)

    # 3. Sort + dedupe
    points = _sort_and_dedupe(points_raw)

    if not points:
        raise HTTPException(404, "No positions found for this vessel in the given period")

    # 4. Route each leg through actual maritime waterways (no land crossings)
    points = await asyncio.to_thread(_apply_maritime_routing, points)

    return TrackResponse(
        mmsi=mmsi,
        name=identity["name"],
        flag=identity["flag"],
        ship_type=identity["ship_type"],
        time_range=f"{start} to {end}",
        point_count=len(points),
        points=[TrackPoint(**p) for p in points],
    )


@app.get("/health")
def health():
    return {"status": "ok", "token_set": bool(GFW_TOKEN)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
