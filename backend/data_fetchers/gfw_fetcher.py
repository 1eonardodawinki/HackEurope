"""
Fetch vessel 1-year path from Global Fishing Watch API.
Called when user presses INVESTIGATE for a given MMSI.
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple
import httpx

from config import GFW_API_TOKEN

BASE_URL = "https://gateway.api.globalfishingwatch.org/v3"
DATASET_IDENTITY = "public-global-vessel-identity:latest"
DATASET_TRACKS = "public-global-vessel-tracks:latest"
MAX_POINTS = 800  # Downsample to ~1 point every ~11 hours for smooth viz
SMOOTH_POINTS_BETWEEN = 18  # Interpolate between event points for smoother voyage-like curve


def _interpolate_segment(points: list[dict], num_between: int) -> list[dict]:
    """Insert interpolated points between each pair for a smoother curve (linear in lat/lon)."""
    if len(points) < 2:
        return points
    out = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        out.append({"lat": a["lat"], "lon": a["lon"]})
        for j in range(1, num_between + 1):
            t = j / (num_between + 1)
            lat = a["lat"] + t * (b["lat"] - a["lat"])
            lon = a["lon"] + t * (b["lon"] - a["lon"])
            out.append({"lat": lat, "lon": lon})
    out.append({"lat": points[-1]["lat"], "lon": points[-1]["lon"]})
    return out


def _apply_maritime_routing(points: list[dict]) -> list[dict]:
    """
    Route each leg between event waypoints through actual navigable sea lanes using
    the searoute library (offline pre-computed shipping graph). Falls back to linear
    interpolation if searoute is unavailable or fails for a given leg.
    """
    try:
        import searoute as sr
    except ImportError:
        return _interpolate_segment(points, SMOOTH_POINTS_BETWEEN)

    if len(points) < 2:
        return points

    out = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        try:
            route = sr.searoute([a["lon"], a["lat"]], [b["lon"], b["lat"]])
            raw_coords = route["geometry"]["coordinates"]  # [[lon, lat], ...]
            for lon, lat in raw_coords[:-1]:
                out.append({"lat": lat, "lon": lon, "timestamp": a.get("timestamp")})
        except Exception:
            seg = _interpolate_segment([a, b], SMOOTH_POINTS_BETWEEN)
            out.extend(seg[:-1])
    out.append(points[-1])
    return out


def _get_vessel_id(mmsi: str) -> Tuple[Optional[str], Optional[dict]]:
    """Search GFW by MMSI, return (vessel_id, vessel_info) or (None, None)."""
    if not GFW_API_TOKEN:
        return None, None

    with httpx.Client(timeout=30) as client:
        r = client.get(
            f"{BASE_URL}/vessels/search",
            params={
                "query": mmsi,
                "datasets[0]": DATASET_IDENTITY,
                "limit": 5,
            },
            headers={"Authorization": f"Bearer {GFW_API_TOKEN}"},
        )
        r.raise_for_status()
        data = r.json()

    entries = data.get("entries") or []
    if not entries:
        return None, None

    entry = entries[0]

    # Prefer selfReportedInfo (AIS) id; fall back to combinedSourcesInfo
    vessel_id = None
    name = "Unknown Vessel"
    ship_type = "Unknown"
    flag = "Unknown"

    for info in entry.get("selfReportedInfo") or []:
        if str(info.get("ssvid", "")) == str(mmsi):
            vessel_id = info.get("id")
            name = info.get("shipname") or info.get("nShipname") or name
            flag = info.get("flag") or flag
            break

    if not vessel_id:
        for info in (entry.get("selfReportedInfo") or [])[:1]:
            vessel_id = info.get("id")
            name = info.get("shipname") or info.get("nShipname") or name
            flag = info.get("flag") or flag
            break

    if not vessel_id and entry.get("combinedSourcesInfo"):
        first = entry["combinedSourcesInfo"][0]
        vessel_id = first.get("vesselId")
        for st in (first.get("shiptypes") or [])[-1:]:
            ship_type = st.get("name", ship_type)

    if not vessel_id:
        return None, None

    reg = (entry.get("registryInfo") or [{}])[0]
    return vessel_id, {
        "name": name or reg.get("shipname") or reg.get("nShipname", "Unknown"),
        "ship_type": ship_type,
        "flag": flag,
    }


def _fetch_tracks(vessel_id: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch track points from GFW. Tracks endpoint returns 404; fallback to Events API."""
    if not GFW_API_TOKEN:
        return []

    # Try tracks endpoint first (may 404 if not available)
    url = f"{BASE_URL}/vessels/{vessel_id}/tracks"
    params = {
        "datasets[0]": DATASET_TRACKS,
        "startDate": start_date,
        "endDate": end_date,
        "format": "json",
    }
    with httpx.Client(timeout=60) as client:
        r = client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {GFW_API_TOKEN}"},
        )
        if r.status_code == 200:
            data = r.json()
            tracks = data.get("tracks") or data.get("features") or []
            if isinstance(tracks, dict):
                tracks = tracks.get("coordinates", tracks.get("geometry", {}).get("coordinates", [])) or []
            result = []
            for t in tracks:
                if isinstance(t, (list, tuple)) and len(t) >= 2:
                    lon, lat = float(t[0]), float(t[1])
                    ts = t[2] if len(t) > 2 else None
                    result.append({"lat": lat, "lon": lon, "timestamp": ts})
                elif isinstance(t, dict):
                    result.append({
                        "lat": float(t.get("latitude", t.get("lat", 0))),
                        "lon": float(t.get("longitude", t.get("lon", 0))),
                        "timestamp": t.get("timestamp"),
                    })
            if result:
                return result
        # Tracks 404 — fallback: Events API (fishing + port visits) for positions
        return _fetch_positions_from_events(client, vessel_id, start_date, end_date)


def _fetch_positions_from_events(
    client: httpx.Client, vessel_id: str, start_date: str, end_date: str
) -> list[dict]:
    """Build path from event positions (fishing, port visits, encounters).
    Note: These are discrete event locations (ports, fishing areas, encounters), not continuous
    voyage track. GFW does not expose a public API for hourly AIS positions per vessel."""
    points: list[dict] = []
    event_datasets = [
        "public-global-fishing-events:latest",
        "public-global-port-visits-events:latest",
        "public-global-encounters-events:latest",
    ]
    for dataset in event_datasets:
        try:
            # Paginate to get more points (up to 2000 total per dataset)
            for offset in range(0, 2000, 500):
                r = client.get(
                    f"{BASE_URL}/events",
                    params={
                        "datasets[0]": dataset,
                        "vessels[0]": vessel_id,
                        "start-date": start_date,
                        "end-date": end_date,
                        "limit": 500,
                        "offset": offset,
                    },
                    headers={"Authorization": f"Bearer {GFW_API_TOKEN}"},
                    timeout=30,
                )
                if r.status_code != 200:
                    break
                data = r.json()
                entries = data.get("entries", data.get("data", []))
                if not isinstance(entries, list) or len(entries) == 0:
                    break
                for e in entries:
                    pos = e.get("position") or e.get("geojson") or e.get("geometry") or {}
                    lat = pos.get("lat") or pos.get("latitude")
                    lon = pos.get("lon") or pos.get("longitude")
                    if lat is None or lon is None:
                        bbox = e.get("boundingBox") or e.get("bounding_box")
                        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
                            lon = (float(bbox[0]) + float(bbox[2])) / 2
                            lat = (float(bbox[1]) + float(bbox[3])) / 2
                        else:
                            coords = pos.get("coordinates", [])
                            if coords:
                                flat = coords
                                while isinstance(flat, (list, tuple)) and flat and isinstance(flat[0], (list, tuple, int, float)):
                                    if isinstance(flat[0], (int, float)) and len(flat) >= 2:
                                        lon, lat = float(flat[0]), float(flat[1])
                                        break
                                    flat = flat[0] if isinstance(flat[0], (list, tuple)) else flat
                                if isinstance(flat, (list, tuple)) and len(flat) >= 2:
                                    lon, lat = float(flat[0]), float(flat[1])
                    if lat is not None and lon is not None:
                        lat, lon = float(lat), float(lon)
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            ts = e.get("start") or e.get("startDate") or e.get("timestamp")
                            points.append({"lat": lat, "lon": lon, "timestamp": ts})
                if len(entries) < 500:
                    break
        except Exception:
            continue

    if not points:
        return []

    # Sort by timestamp (parse ISO for proper order)
    def sort_key(p):
        t = p.get("timestamp") or ""
        if isinstance(t, str) and "T" in t:
            try:
                from datetime import datetime
                return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
            except Exception:
                return str(t)
        return str(t)

    points.sort(key=sort_key)

    # Dedupe nearby points and split into segments when gap > ~800km
    # (avoids drawing lines across land when connecting disjoint voyages)
    KM_PER_DEG_APPROX = 111
    MAX_GAP_KM = 800
    segments = []
    current = []
    last_lat = last_lon = None
    for p in points:
        lat, lon = p["lat"], p["lon"]
        if last_lat is not None:
            dlat = (lat - last_lat) * KM_PER_DEG_APPROX
            dlon = (lon - last_lon) * KM_PER_DEG_APPROX * 0.7
            gap_km = (dlat ** 2 + dlon ** 2) ** 0.5
            if gap_km > MAX_GAP_KM and len(current) >= 2:
                segments.append(current)
                current = []
        if last_lat is None or abs(lat - last_lat) > 0.05 or abs(lon - last_lon) > 0.05:
            current.append({"lat": lat, "lon": lon, "timestamp": p.get("timestamp")})
            last_lat, last_lon = lat, lon
    if len(current) >= 2:
        segments.append(current)
    if not segments:
        return []

    # Route each leg through actual maritime sea lanes (avoids drawing across land).
    # searoute uses a pre-computed shipping graph; falls back to linear interpolation
    # for any leg where routing fails.
    smoothed = []
    for seg in segments:
        routed = _apply_maritime_routing(seg)
        smoothed.append(routed)
    return smoothed[0] if len(smoothed) == 1 else smoothed


def fetch_vessel_path(mmsi: str) -> dict:
    """
    Fetch 1-year path for vessel by MMSI.
    Returns {
        "mmsi": str,
        "metadata": { name, ship_type, flag, point_count, time_range },
        "path": [{ lat, lon, timestamp? }],
        "error": str | None
    }
    """
    mmsi = str(mmsi).strip()
    out = {
        "mmsi": mmsi,
        "metadata": {"name": "Unknown", "ship_type": "Unknown", "flag": "?", "point_count": 0, "time_range": ""},
        "path": [],
        "error": None,
    }

    if not GFW_API_TOKEN:
        out["error"] = "GFW_API_TOKEN not configured"
        return out

    vessel_id, vessel_info = _get_vessel_id(mmsi)
    if not vessel_id:
        out["error"] = "Vessel not found in Global Fishing Watch"
        return out

    out["metadata"]["name"] = vessel_info.get("name", "Unknown")
    out["metadata"]["ship_type"] = vessel_info.get("ship_type", "Unknown")
    out["metadata"]["flag"] = vessel_info.get("flag", "?")

    end = datetime.utcnow()
    start = end - timedelta(days=365)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    out["metadata"]["time_range"] = f"{start_str} to {end_str}"

    try:
        points = _fetch_tracks(vessel_id, start_str, end_str)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            out["error"] = "Track data not available for this vessel"
        else:
            out["error"] = f"GFW API error: {e.response.status_code}"
        return out
    except Exception as e:
        out["error"] = f"Failed to fetch track: {e!s}"
        return out

    if not points:
        out["error"] = "No track points returned"
        return out

    # Normalize: points is either list of dicts (single segment) or list of lists (multi-segment)
    if points and isinstance(points[0], list):
        segments = points
    else:
        segments = [points]

    flat = [p for seg in segments for p in seg]
    if len(flat) > MAX_POINTS:
        step = max(1, len(flat) // MAX_POINTS)
        flat = flat[::step]
        segments = [flat]

    out["path"] = [{"lat": p["lat"], "lon": p["lon"], "timestamp": p.get("timestamp")} for p in flat]
    out["path_segments"] = [[{"lat": p["lat"], "lon": p["lon"]} for p in seg] for seg in segments]
    out["metadata"]["point_count"] = len(out["path"])
    out["metadata"]["data_source"] = "event_locations"  # Ports, fishing, encounters; path smoothed by interpolation

    return out
