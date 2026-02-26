"""
Maritime Sentinel — FastAPI backend
Streams live ship positions and intelligence alerts via WebSocket.
"""

import asyncio
import json
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import HOTZONES, DEMO_MODE, AISSTREAM_API_KEY
from report_renderer import render_pdf
from ais_monitor import AISMonitor
from incident_detector import IncidentDetector
from ml_model import get_dark_fleet_probability
from agents.investigation_agents import run_parallel_investigation
from agents.reporter_agent import generate_investigation_report
from data_fetchers.gfw_fetcher import fetch_vessel_path
from local_mmsi_context import load_mmsi_context
import database as db

HISTORICAL_DB_PATH = os.path.join(os.path.dirname(__file__), "historical_unmatched.db")


def fetch_unmatched_points(mmsi: str) -> dict[str, Any]:
    """Return all unmatched historical points for an MMSI from local SQLite."""
    if not os.path.exists(HISTORICAL_DB_PATH):
        return {
            "mmsi": mmsi,
            "points": [],
            "metadata": {"point_count": 0, "data_source": "historical_unmatched"},
            "error": "historical_unmatched.db not found",
        }

    conn = sqlite3.connect(HISTORICAL_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT lat, lon, timestamp
            FROM historical_detections
            WHERE CAST(mmsi AS TEXT) = ?
              AND lat IS NOT NULL
              AND lon IS NOT NULL
            ORDER BY timestamp
            """,
            (mmsi,),
        ).fetchall()
    finally:
        conn.close()

    points = [
        {
            "lat": row["lat"],
            "lon": row["lon"],
            "timestamp": row["timestamp"],
        }
        for row in rows
    ]
    return {
        "mmsi": mmsi,
        "points": points,
        "metadata": {
            "point_count": len(points),
            "data_source": "historical_unmatched",
        },
    }

# ── WebSocket Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.clients: dict[str, WebSocket] = {}  # client_id → websocket

    async def connect(self, ws: WebSocket) -> str:
        """Accept connection, assign a unique client_id, return it."""
        client_id = str(uuid.uuid4())
        await ws.accept()
        self.clients[client_id] = ws
        return client_id

    def disconnect(self, client_id: str):
        self.clients.pop(client_id, None)

    async def broadcast(self, message: dict):
        """Send to all connected clients (used for shared state: ships, mode)."""
        dead = []
        payload = json.dumps(message)
        for cid, ws in list(self.clients.items()):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.clients.pop(cid, None)

    async def send_to(self, client_id: str, message: dict):
        """Send a message to one specific client only."""
        ws = self.clients.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                self.clients.pop(client_id, None)


manager = ConnectionManager()
detector: IncidentDetector | None = None
monitor: AISMonitor | None = None
_ais_task: asyncio.Task | None = None
_current_demo_mode: bool = DEMO_MODE
_active_hotzones: dict = dict(HOTZONES)  # Mutable at runtime via POST/DELETE /hotzones
# Per-client investigation tasks: client_id → asyncio.Task
_investigation_tasks: dict[str, asyncio.Task] = {}


# ── Module-level AIS callbacks (so they can be reused on mode switch) ─────────

async def _on_ship_update(ships: list[dict]):
    await manager.broadcast({"type": "ships", "data": ships})
    asyncio.create_task(db.record_ship_positions(ships))

async def _on_incident(incident: dict):
    pass  # Investigation-mode only — incidents are triggered manually via POST /investigate


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector, monitor, _ais_task, _current_demo_mode

    _current_demo_mode = DEMO_MODE

    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    try:
        # Load persisted zones; seed DB with defaults if empty
        zones_from_db = await db.load_zones()
        if zones_from_db:
            _active_hotzones = zones_from_db
            print(f"[Zones] Loaded {len(_active_hotzones)} zone(s) from DB")
        else:
            _active_hotzones = dict(HOTZONES)
            for name, zone in HOTZONES.items():
                asyncio.create_task(db.save_zone(name, zone))
            print(f"[Zones] Seeded DB with {len(_active_hotzones)} default zone(s)")

        detector = IncidentDetector(broadcast_callback=broadcast)
        monitor = AISMonitor(
            on_ship_update=_on_ship_update,
            on_incident=_on_incident,
            demo_mode=_current_demo_mode,
        )
        monitor.update_zones(_active_hotzones)
        _ais_task = asyncio.create_task(monitor.start())
    except Exception as e:
        # Never fail process startup because monitoring init failed; keep API/health alive.
        import traceback
        print(f"[Startup] Monitoring init failed: {e}")
        traceback.print_exc()
        detector = IncidentDetector(broadcast_callback=broadcast)
        monitor = None
        _ais_task = None

    yield  # App running

    if monitor:
        monitor.stop()
    if _ais_task:
        _ais_task.cancel()
        try:
            await _ais_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Maritime Sentinel", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "ships": len(monitor.get_ships()) if monitor else 0}


@app.get("/ships")
async def get_ships():
    return monitor.get_ships() if monitor else []


@app.get("/hotzones")
async def get_hotzones():
    return _active_hotzones


class ZoneRequest(BaseModel):
    name: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    center_lat: float | None = None
    center_lon: float | None = None
    color: str = "#ff6b00"
    description: str = ""
    commodities: list[str] = []


@app.post("/hotzones")
async def add_hotzone(req: ZoneRequest):
    global _active_hotzones
    _active_hotzones[req.name] = {
        "min_lat": req.min_lat, "max_lat": req.max_lat,
        "min_lon": req.min_lon, "max_lon": req.max_lon,
        "center_lat": req.center_lat if req.center_lat is not None else (req.min_lat + req.max_lat) / 2,
        "center_lon": req.center_lon if req.center_lon is not None else (req.min_lon + req.max_lon) / 2,
        "color": req.color,
        "description": req.description,
        "commodities": req.commodities,
    }
    if monitor:
        monitor.update_zones(_active_hotzones)
    asyncio.create_task(db.save_zone(req.name, _active_hotzones[req.name]))
    return {"status": "added", "name": req.name, "total_zones": len(_active_hotzones)}


@app.delete("/hotzones/{name:path}")
async def delete_hotzone(name: str):
    global _active_hotzones
    if name not in _active_hotzones:
        return {"status": "not_found", "name": name}
    del _active_hotzones[name]
    if monitor:
        monitor.update_zones(_active_hotzones)
    asyncio.create_task(db.delete_zone(name))
    return {"status": "deleted", "name": name, "total_zones": len(_active_hotzones)}


@app.get("/summary")
async def get_summary():
    return detector.get_summary() if detector else {}


@app.get("/history/incidents")
async def get_incident_history(region: str = None, limit: int = 50):
    return await db.get_recent_incidents(region=region, limit=limit)


@app.get("/history/reports")
async def get_report_history(limit: int = 10):
    return await db.get_recent_reports(limit=limit)


# ── Mode Switch ───────────────────────────────────────────────────────────────

class ModeRequest(BaseModel):
    demo: bool


class AbortRequest(BaseModel):
    client_id: str = ""


class InvestigationRequest(BaseModel):
    mmsi: str
    vessel_name: str = ""
    flag_state: str = ""
    region: str = ""
    client_id: str = ""


async def _run_investigation(
    mmsi: str,
    vessel_name: str,
    flag_state: str,
    region: str,
    client_id: str,
    local_data: dict | None = None,
):
    """Background task: run the full investigation pipeline for one client."""
    vessel_info = {
        "mmsi": mmsi,
        "vessel_name": vessel_name,
        "flag_state": flag_state,
        "region": region,
        "local_data": local_data or {},
    }

    async def progress(msg: dict):
        await manager.send_to(client_id, {"type": "agent_status", "data": msg})

    print(f"[Investigate] Starting pipeline for MMSI {mmsi} (client {client_id[:8]})")
    await manager.send_to(client_id, {
        "type": "agent_status",
        "data": {"stage": "investigation", "message": f"Investigation started for MMSI {mmsi}..."},
    })

    try:
        ml_score = await get_dark_fleet_probability(mmsi, vessel_name)
        print(f"[Investigate] ML score: {ml_score['probability']:.0%} ({ml_score['risk_tier']})")
        await manager.send_to(client_id, {
            "type": "agent_status",
            "data": {
                "stage": "investigation",
                "message": f"ML model: {ml_score['risk_tier']} risk ({ml_score['probability']:.0%}) — launching agents...",
            },
        })

        agent_findings = await run_parallel_investigation(vessel_info, progress_callback=progress)

        report = await generate_investigation_report(
            vessel_info, ml_score, agent_findings, progress_callback=progress
        )

        await manager.send_to(client_id, {"type": "report", "data": report})
        print(f"[Investigate] Report sent to client {client_id[:8]} for MMSI {mmsi}")

    except asyncio.CancelledError:
        print(f"[Investigate] Task cancelled for MMSI {mmsi} (client {client_id[:8]})")
        await manager.send_to(client_id, {
            "type": "agent_status",
            "data": {"stage": "aborted", "message": f"Investigation aborted for MMSI {mmsi}"},
        })
    except Exception:
        import traceback
        traceback.print_exc()
        await manager.send_to(client_id, {
            "type": "agent_status",
            "data": {"stage": "error", "message": f"Investigation failed for MMSI {mmsi}"},
        })
    finally:
        _investigation_tasks.pop(client_id, None)


@app.post("/investigate/abort")
async def abort_investigation(body: AbortRequest):
    """Cancel the running investigation task for a specific client."""
    task = _investigation_tasks.get(body.client_id)
    if task and not task.done():
        task.cancel()
        return {"status": "aborted"}
    return {"status": "no_active_investigation"}


@app.post("/investigate")
async def investigate(body: InvestigationRequest):
    mmsi = body.mmsi.strip()

    # Auto-enrich from current AIS feed if the vessel is tracked
    current_ships = monitor.get_ships() if monitor else []
    vessel = next((s for s in current_ships if str(s.get("mmsi", "")) == mmsi), None)
    vessel_name = vessel.get("name", "") if vessel else body.vessel_name.strip()
    region = (vessel.get("in_hotzone") or body.region.strip()) if vessel else body.region.strip()
    flag_state = body.flag_state.strip()

    # Broadcast vessel location to all clients so the map can highlight it
    if vessel:
        await manager.broadcast({
            "type": "investigation_start",
            "data": {"mmsi": mmsi, "vessel": vessel},
        })

    client_id = body.client_id
    # Cancel any running investigation for this client before starting a new one
    existing = _investigation_tasks.get(client_id)
    if existing and not existing.done():
        existing.cancel()
    local_data = await asyncio.to_thread(load_mmsi_context, mmsi)
    _investigation_tasks[client_id] = asyncio.create_task(
        _run_investigation(mmsi, vessel_name, flag_state, region, client_id=client_id, local_data=local_data)
    )

    # Fetch GFW 1-year path — send only to the requesting client
    async def _send_gfw_path():
        try:
            result = await asyncio.to_thread(fetch_vessel_path, mmsi)
            await manager.send_to(client_id, {"type": "gfw_path", "data": result})
        except Exception:
            await manager.send_to(client_id, {
                "type": "gfw_path",
                "data": {"mmsi": mmsi, "error": "Failed to fetch vessel path", "path": [], "metadata": {}},
            })
    asyncio.create_task(_send_gfw_path())

    async def _send_unmatched_points():
        try:
            result = await asyncio.to_thread(fetch_unmatched_points, mmsi)
            await manager.send_to(client_id, {"type": "unmatched_points", "data": result})
        except Exception:
            await manager.send_to(client_id, {
                "type": "unmatched_points",
                "data": {
                    "mmsi": mmsi,
                    "points": [],
                    "metadata": {"point_count": 0, "data_source": "historical_unmatched"},
                    "error": "Failed to fetch unmatched historical points",
                },
            })
    asyncio.create_task(_send_unmatched_points())

    return {"status": "started", "mmsi": mmsi}


@app.get("/gfw-path")
async def get_gfw_path(mmsi: str):
    """Fetch GFW 1-year path only (no full investigation). Returns path data for map."""
    mmsi = mmsi.strip()
    if not mmsi:
        return {"error": "MMSI required", "path": [], "metadata": {}}
    try:
        result = await asyncio.to_thread(fetch_vessel_path, mmsi)
        await manager.broadcast({"type": "gfw_path", "data": result})
        return result
    except Exception:
        return {"mmsi": mmsi, "error": "Failed to fetch path", "path": [], "metadata": {}}


@app.get("/dark-events")
async def get_dark_events(limit: int = 4000):
    """Return a sampled set of unmatched SAR detections (vessels with no AIS = went dark)."""
    def _fetch():
        if not os.path.exists(HISTORICAL_DB_PATH):
            return {"points": [], "total": 0}
        conn = sqlite3.connect(HISTORICAL_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM historical_detections WHERE mmsi IS NULL OR mmsi = '' OR mmsi = 'None'"
            ).fetchone()[0]
            rows = conn.execute(
                """
                SELECT lat, lon, timestamp
                FROM historical_detections
                WHERE (mmsi IS NULL OR mmsi = '' OR mmsi = 'None')
                  AND lat IS NOT NULL AND lon IS NOT NULL
                ORDER BY RANDOM()
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        finally:
            conn.close()
        return {
            "points": [{"lat": r["lat"], "lon": r["lon"], "timestamp": r["timestamp"]} for r in rows],
            "total": total,
        }
    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return {"points": [], "total": 0}


@app.get("/historical-unmatched")
async def get_historical_unmatched(mmsi: str):
    """Fetch unmatched historical points for map overlay."""
    mmsi = mmsi.strip()
    if not mmsi:
        return {
            "error": "MMSI required",
            "mmsi": "",
            "points": [],
            "metadata": {"point_count": 0, "data_source": "historical_unmatched"},
        }
    try:
        result = await asyncio.to_thread(fetch_unmatched_points, mmsi)
        await manager.broadcast({"type": "unmatched_points", "data": result})
        return result
    except Exception:
        return {
            "mmsi": mmsi,
            "error": "Failed to fetch unmatched historical points",
            "points": [],
            "metadata": {"point_count": 0, "data_source": "historical_unmatched"},
        }


@app.post("/mode")
async def switch_mode(body: ModeRequest):
    global detector, monitor, _ais_task, _current_demo_mode

    # If already in the requested mode, still broadcast so the frontend can resync
    if body.demo == _current_demo_mode:
        await manager.broadcast({
            "type": "mode_change",
            "data": {"demo_mode": _current_demo_mode, "has_live_key": True},
        })
        return {"demo_mode": _current_demo_mode}

    # Stop existing monitor — catch ALL exceptions, not just CancelledError,
    # so a network error during teardown can never block the mode_change broadcast
    if monitor:
        monitor.stop()
    if _ais_task:
        _ais_task.cancel()
        try:
            await _ais_task
        except BaseException:
            pass

    _current_demo_mode = body.demo

    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    detector = IncidentDetector(broadcast_callback=broadcast)
    monitor = AISMonitor(on_ship_update=_on_ship_update, on_incident=_on_incident, demo_mode=_current_demo_mode)
    monitor.update_zones(_active_hotzones)
    _ais_task = asyncio.create_task(monitor.start())

    await manager.broadcast({
        "type": "mode_change",
        "data": {"demo_mode": _current_demo_mode, "has_live_key": True},
    })

    print(f"[Mode] Switched to {'DEMO' if _current_demo_mode else 'LIVE'} mode")
    return {"demo_mode": _current_demo_mode}


# ── Report PDF ────────────────────────────────────────────────────────────────

@app.post("/report/pdf")
async def generate_pdf(report: dict = Body(...)):
    """Generate a PDF from a report dict using ReportLab (no LaTeX required)."""
    try:
        pdf_bytes = render_pdf(report)
        print(f"[PDF] Generated {len(pdf_bytes):,} byte PDF")
        return Response(
            content=pdf_bytes,
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="intelligence-report.pdf"'},
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[PDF] render_pdf error: {e}")
        return Response(
            content=f"PDF generation failed: {e}".encode('utf-8'),
            media_type='text/plain; charset=utf-8',
            status_code=500,
        )


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_id = await manager.connect(websocket)
    try:
        # Send initial state with client_id so the frontend can tag requests
        await manager.send_to(client_id, {
            "type": "init",
            "data": {
                "client_id": client_id,
                "ships": monitor.get_ships() if monitor else [],
                "hotzones": _active_hotzones,
                "summary": detector.get_summary() if detector else {},
                "demo_mode": _current_demo_mode,
                "has_live_key": True,
            }
        })

        # Keep connection alive and handle any client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await manager.send_to(client_id, {"type": "pong"})
            except asyncio.TimeoutError:
                await manager.send_to(client_id, {"type": "heartbeat"})
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        manager.disconnect(client_id)
        # Cancel any running investigation for this client when they disconnect
        task = _investigation_tasks.pop(client_id, None)
        if task and not task.done():
            task.cancel()


# ── Serve built frontend (production) ─────────────────────────────────────────

STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve the React SPA for any non-API route."""
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
