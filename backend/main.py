"""
Maritime Sentinel — FastAPI backend
Streams live ship positions and intelligence alerts via WebSocket.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import HOTZONES, DEMO_MODE, AISSTREAM_API_KEY
from ais_monitor import AISMonitor
from incident_detector import IncidentDetector
from ml_model import get_dark_fleet_probability
from agents.investigation_agents import run_parallel_investigation
from agents.reporter_agent import generate_investigation_report
import database as db

# ── WebSocket Manager ─────────────────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = set()
        payload = json.dumps(message)
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.active.discard(ws)


manager = ConnectionManager()
detector: IncidentDetector | None = None
monitor: AISMonitor | None = None
_ais_task: asyncio.Task | None = None
_current_demo_mode: bool = DEMO_MODE


# ── Module-level AIS callbacks (so they can be reused on mode switch) ─────────

async def _on_ship_update(ships: list[dict]):
    await manager.broadcast({"type": "ships", "data": ships})
    asyncio.create_task(db.record_ship_positions(ships))

async def _on_incident(incident: dict):
    if detector:
        await detector.add_incident(incident)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector, monitor, _ais_task, _current_demo_mode

    _current_demo_mode = DEMO_MODE

    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    detector = IncidentDetector(broadcast_callback=broadcast)
    monitor = AISMonitor(on_ship_update=_on_ship_update, on_incident=_on_incident, demo_mode=_current_demo_mode)
    _ais_task = asyncio.create_task(monitor.start())

    yield  # App running

    monitor.stop()
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
    return HOTZONES


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


class InvestigationRequest(BaseModel):
    mmsi: str
    vessel_name: str = ""
    flag_state: str = ""
    region: str = ""


async def _run_investigation(mmsi: str, vessel_name: str, flag_state: str, region: str):
    """Background task: run the full investigation pipeline and broadcast results."""
    vessel_info = {"mmsi": mmsi, "vessel_name": vessel_name, "flag_state": flag_state, "region": region}

    async def progress(msg: dict):
        await manager.broadcast({"type": "agent_status", "data": msg})

    print(f"[Investigate] Starting pipeline for MMSI {mmsi}")
    await manager.broadcast({
        "type": "agent_status",
        "data": {"stage": "investigation", "message": f"Investigation started for MMSI {mmsi}..."},
    })

    try:
        ml_score = await get_dark_fleet_probability(mmsi, vessel_name)
        print(f"[Investigate] ML score: {ml_score['probability']:.0%} ({ml_score['risk_tier']})")
        await manager.broadcast({
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

        await manager.broadcast({"type": "report", "data": report})
        print(f"[Investigate] Report broadcast for MMSI {mmsi}")

    except Exception:
        import traceback
        traceback.print_exc()
        await manager.broadcast({
            "type": "agent_status",
            "data": {"stage": "error", "message": f"Investigation failed for MMSI {mmsi}"},
        })


@app.post("/investigate")
async def investigate(body: InvestigationRequest):
    asyncio.create_task(_run_investigation(
        body.mmsi.strip(), body.vessel_name.strip(), body.flag_state.strip(), body.region.strip()
    ))
    return {"status": "started", "mmsi": body.mmsi}


@app.post("/mode")
async def switch_mode(body: ModeRequest):
    global detector, monitor, _ais_task, _current_demo_mode

    if body.demo == _current_demo_mode:
        return {"demo_mode": _current_demo_mode}

    # Stop existing monitor
    if monitor:
        monitor.stop()
    if _ais_task:
        _ais_task.cancel()
        try:
            await _ais_task
        except asyncio.CancelledError:
            pass

    _current_demo_mode = body.demo

    # Fresh detector so incident counts reset for the new session
    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    detector = IncidentDetector(broadcast_callback=broadcast)
    monitor = AISMonitor(on_ship_update=_on_ship_update, on_incident=_on_incident, demo_mode=_current_demo_mode)
    _ais_task = asyncio.create_task(monitor.start())

    # Tell all connected clients to reset their state
    await manager.broadcast({
        "type": "mode_change",
        "data": {
            "demo_mode": _current_demo_mode,
            "has_live_key": bool(AISSTREAM_API_KEY),
        },
    })

    print(f"[Mode] Switched to {'DEMO' if _current_demo_mode else 'LIVE'} mode")
    return {"demo_mode": _current_demo_mode}


# ── WebSocket Endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state immediately
        if monitor:
            await websocket.send_text(json.dumps({
                "type": "init",
                "data": {
                    "ships": monitor.get_ships(),
                    "hotzones": HOTZONES,
                    "summary": detector.get_summary() if detector else {},
                    "demo_mode": _current_demo_mode,
                    "has_live_key": bool(AISSTREAM_API_KEY),
                }
            }))

        # Keep connection alive and handle any client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)