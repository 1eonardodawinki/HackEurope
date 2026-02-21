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

from config import HOTZONES
from ais_monitor import AISMonitor
from incident_detector import IncidentDetector
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


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global detector, monitor

    async def broadcast(msg: dict):
        await manager.broadcast(msg)

    async def on_ship_update(ships: list[dict]):
        await manager.broadcast({"type": "ships", "data": ships})
        # Persist hotzone ships to Supabase (batched, fire-and-forget)
        asyncio.create_task(db.record_ship_positions(ships))

    async def on_incident(incident: dict):
        await detector.add_incident(incident)

    detector = IncidentDetector(broadcast_callback=broadcast)
    monitor = AISMonitor(on_ship_update=on_ship_update, on_incident=on_incident)

    # Start AIS monitor as a background task
    ais_task = asyncio.create_task(monitor.start())

    yield  # App running

    monitor.stop()
    ais_task.cancel()
    try:
        await ais_task
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
                }
            }))

        # Keep connection alive and handle any client messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                msg = json.loads(data)
                # Handle ping/pong
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
            except WebSocketDisconnect:
                break
    except Exception:
        pass
    finally:
        manager.disconnect(websocket)
