"""
AIS Monitor — handles real AIS data from AISstream.io or simulation.

In DEMO_MODE:
  - Generates realistic ship positions across the globe
  - Simulates incident triggers (AIS dropout + proximity) at configured intervals
  - Returns ship data in the same format as the real feed

In LIVE mode:
  - Connects to wss://stream.aisstream.io/v0/stream
  - Filters ships in hotzone bounding boxes
"""

import asyncio
import json
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Callable, Awaitable

import websockets

from config import (
    AISSTREAM_API_KEY, DEMO_MODE, HOTZONES,
    DEMO_SHIP_COUNT, DEMO_INCIDENT_DELAY_SECONDS, DEMO_INCIDENT_INTERVAL_SECONDS,
)

# ── Utility ───────────────────────────────────────────────────────────────────

def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    """Distance in nautical miles between two lat/lon points."""
    R = 3440.065  # Earth radius in NM
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def in_any_hotzone(lat: float, lon: float) -> str | None:
    for name, hz in HOTZONES.items():
        if hz["min_lat"] <= lat <= hz["max_lat"] and hz["min_lon"] <= lon <= hz["max_lon"]:
            return name
    return None


# ── Demo Ship Generator ───────────────────────────────────────────────────────

DEMO_SHIPS_SPEC = [
    # Strait of Hormuz traffic
    {"mmsi": 311000001, "name": "GULF PIONEER", "lat": 25.8, "lon": 56.2, "cog": 120, "sog": 11.0, "type": "tanker"},
    {"mmsi": 311000002, "name": "HORMUZ TRADER", "lat": 26.2, "lon": 57.1, "cog": 300, "sog": 9.5,  "type": "tanker"},
    {"mmsi": 311000003, "name": "PERSIAN STAR",  "lat": 25.5, "lon": 58.0, "cog": 270, "sog": 13.0, "type": "tanker"},
    {"mmsi": 311000004, "name": "FALCON SPIRIT", "lat": 26.5, "lon": 56.8, "cog": 90,  "sog": 7.5,  "type": "cargo"},
    {"mmsi": 311000005, "name": "ARABIAN CROWN", "lat": 25.9, "lon": 57.5, "cog": 280, "sog": 10.0, "type": "tanker"},
    # Black Sea traffic
    {"mmsi": 212000001, "name": "BLACK SEA VENTURE", "lat": 43.0, "lon": 31.5, "cog": 50,  "sog": 12.0, "type": "bulk_carrier"},
    {"mmsi": 212000002, "name": "ODESSA SPIRIT",     "lat": 44.5, "lon": 33.0, "cog": 220, "sog": 8.5,  "type": "tanker"},
    {"mmsi": 212000003, "name": "BOSPHORUS KING",    "lat": 42.0, "lon": 29.5, "cog": 45,  "sog": 14.0, "type": "container"},
    {"mmsi": 212000004, "name": "DANUBE DREAM",      "lat": 45.5, "lon": 30.5, "cog": 180, "sog": 7.0,  "type": "bulk_carrier"},
    # Red Sea traffic
    {"mmsi": 538000001, "name": "SUEZ EXPRESS",   "lat": 27.0, "lon": 33.5, "cog": 160, "sog": 15.0, "type": "container"},
    {"mmsi": 538000002, "name": "RED SEA GLORY",  "lat": 20.5, "lon": 38.2, "cog": 350, "sog": 11.0, "type": "tanker"},
    {"mmsi": 538000003, "name": "ADEN CARRIER",   "lat": 14.0, "lon": 42.5, "cog": 170, "sog": 9.0,  "type": "cargo"},
    # Global traffic (outside hotzones — background)
    {"mmsi": 636000001, "name": "ATLANTIC HORIZON",  "lat": 35.0, "lon": -10.0, "cog": 75,  "sog": 16.0, "type": "container"},
    {"mmsi": 636000002, "name": "PACIFIC STAR",      "lat": 20.0, "lon": 120.0, "cog": 280, "sog": 14.5, "type": "container"},
    {"mmsi": 636000003, "name": "CAPE GLORY",        "lat": -34.0,"lon": 18.0,  "cog": 90,  "sog": 12.0, "type": "bulk_carrier"},
    {"mmsi": 636000004, "name": "NORTHERN SPIRIT",   "lat": 55.0, "lon": 0.0,   "cog": 200, "sog": 10.0, "type": "tanker"},
    {"mmsi": 636000005, "name": "MEDITERRANEAN SUN", "lat": 38.0, "lon": 18.0,  "cog": 135, "sog": 13.0, "type": "cargo"},
    {"mmsi": 636000006, "name": "INDIAN OCEAN STAR", "lat": 10.0, "lon": 65.0,  "cog": 250, "sog": 11.5, "type": "tanker"},
    {"mmsi": 636000007, "name": "CHINA SEA EAGLE",   "lat": 30.0, "lon": 125.0, "cog": 315, "sog": 15.0, "type": "container"},
    {"mmsi": 636000008, "name": "WEST AFRICA PRIDE", "lat": 5.0,  "lon": 0.0,   "cog": 45,  "sog": 9.0,  "type": "bulk_carrier"},
    {"mmsi": 636000009, "name": "GULF OF MEXICO WAVE","lat": 25.0, "lon": -90.0, "cog": 95,  "sog": 8.0,  "type": "tanker"},
    {"mmsi": 636000010, "name": "NORTH SEA RANGER",  "lat": 58.0, "lon": 3.0,   "cog": 270, "sog": 12.0, "type": "cargo"},
    {"mmsi": 636000011, "name": "SUEZ MARINER",      "lat": 30.0, "lon": 32.0,  "cog": 340, "sog": 14.0, "type": "container"},
    {"mmsi": 636000012, "name": "BAY OF BENGAL",     "lat": 15.0, "lon": 85.0,  "cog": 200, "sog": 10.5, "type": "bulk_carrier"},
]

# The "dark" ship — will go AIS-dark during demo
DARK_SHIP_MMSI = 311000003  # PERSIAN STAR

# The "ghost" ship that appears next to the dark ship (simulating STS rendezvous)
GHOST_SHIP = {
    "mmsi": 999000001,
    "name": "UNKNOWN VESSEL",
    "lat": 25.52,
    "lon": 58.02,
    "cog": 90,
    "sog": 0.2,
    "type": "tanker",
}


class AISMonitor:
    def __init__(self, on_ship_update: Callable, on_incident: Callable):
        self.on_ship_update = on_ship_update   # async callback(ships: list[dict])
        self.on_incident = on_incident         # async callback(incident: dict)

        # State
        self._ships: dict[int, dict] = {}     # mmsi → ship dict
        self._running = False
        self._incident_count = 0

        # Initialise demo ships
        if DEMO_MODE:
            for spec in DEMO_SHIPS_SPEC:
                self._ships[spec["mmsi"]] = {**spec, "trail": [], "status": "active", "in_hotzone": in_any_hotzone(spec["lat"], spec["lon"])}

    # ── Public API ────────────────────────────────────────────────────────────

    async def start(self):
        self._running = True
        if DEMO_MODE:
            await asyncio.gather(
                self._demo_movement_loop(),
                self._demo_incident_loop(),
            )
        else:
            await self._live_ais_loop()

    def stop(self):
        self._running = False

    def get_ships(self) -> list[dict]:
        return [self._serialise(s) for s in self._ships.values()]

    # ── Demo loops ────────────────────────────────────────────────────────────

    async def _demo_movement_loop(self):
        """Move demo ships every 5 seconds and broadcast positions."""
        while self._running:
            for mmsi, ship in list(self._ships.items()):
                if ship.get("status") == "dark":
                    continue  # Dark ships don't transmit

                # Move ship along its course
                lat, lon, sog, cog = ship["lat"], ship["lon"], ship["sog"], ship["cog"]
                speed_deg_per_sec = sog * 0.000083333  # knots → deg/s (approx)
                dt = 5  # seconds
                dlat = speed_deg_per_sec * dt * math.cos(math.radians(cog))
                dlon = speed_deg_per_sec * dt * math.sin(math.radians(cog)) / math.cos(math.radians(lat + 0.001))
                ship["lat"] = lat + dlat + random.uniform(-0.0002, 0.0002)
                ship["lon"] = lon + dlon + random.uniform(-0.0002, 0.0002)

                # Small random heading variation
                ship["cog"] = (cog + random.uniform(-1.5, 1.5)) % 360

                # Update trail (keep last 20 positions)
                ship["trail"].append([ship["lon"], ship["lat"]])
                if len(ship["trail"]) > 20:
                    ship["trail"] = ship["trail"][-20:]

                ship["in_hotzone"] = in_any_hotzone(ship["lat"], ship["lon"])
                ship["last_seen"] = datetime.now(timezone.utc).isoformat()

            await self.on_ship_update(self.get_ships())
            await asyncio.sleep(5)

    async def _demo_incident_loop(self):
        """After a delay, trigger simulated incidents to drive the AI pipeline."""
        await asyncio.sleep(DEMO_INCIDENT_DELAY_SECONDS)

        while self._running:
            self._incident_count += 1
            incident_num = self._incident_count

            if incident_num == 1:
                # First incident: PERSIAN STAR goes dark in Strait of Hormuz
                ship = self._ships.get(DARK_SHIP_MMSI)
                if ship:
                    ship["status"] = "dark"
                    await self.on_incident({
                        "id": f"INC-{incident_num:03d}",
                        "type": "ais_dropout",
                        "mmsi": DARK_SHIP_MMSI,
                        "ship_name": ship["name"],
                        "lat": ship["lat"],
                        "lon": ship["lon"],
                        "region": "Strait of Hormuz",
                        "duration_minutes": 0,
                        "nearby_ships": [],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": "medium",
                    })

            elif incident_num == 2:
                # Second incident: Ghost ship appears next to dark ship (STS rendezvous)
                dark_ship = self._ships.get(DARK_SHIP_MMSI)
                if dark_ship:
                    ghost = {**GHOST_SHIP}
                    ghost["lat"] = dark_ship["lat"] + 0.008
                    ghost["lon"] = dark_ship["lon"] + 0.006
                    ghost["trail"] = []
                    ghost["status"] = "suspicious"
                    ghost["in_hotzone"] = "Strait of Hormuz"
                    ghost["last_seen"] = datetime.now(timezone.utc).isoformat()
                    self._ships[GHOST_SHIP["mmsi"]] = ghost

                    await self.on_incident({
                        "id": f"INC-{incident_num:03d}",
                        "type": "ship_proximity",
                        "mmsi": GHOST_SHIP["mmsi"],
                        "ship_name": "UNKNOWN VESSEL",
                        "lat": ghost["lat"],
                        "lon": ghost["lon"],
                        "region": "Strait of Hormuz",
                        "duration_minutes": 18,
                        "nearby_ships": [{"mmsi": DARK_SHIP_MMSI, "name": "PERSIAN STAR (DARK)", "distance_nm": 0.3}],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": "high",
                    })

            elif incident_num == 3:
                # Third incident: Black Sea tanker goes dark
                bs_ship = self._ships.get(212000002)
                if bs_ship:
                    bs_ship["status"] = "dark"
                    await self.on_incident({
                        "id": f"INC-{incident_num:03d}",
                        "type": "ais_dropout",
                        "mmsi": 212000002,
                        "ship_name": bs_ship["name"],
                        "lat": bs_ship["lat"],
                        "lon": bs_ship["lon"],
                        "region": "Black Sea",
                        "duration_minutes": 28,
                        "nearby_ships": [],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "severity": "medium",
                    })

            await asyncio.sleep(DEMO_INCIDENT_INTERVAL_SECONDS)

    # ── Live AIS loop ─────────────────────────────────────────────────────────

    async def _live_ais_loop(self):
        """Connect to AISstream.io WebSocket and process real AIS data."""
        url = "wss://stream.aisstream.io/v0/stream"

        bboxes = [
            [[hz["min_lat"], hz["min_lon"]], [hz["max_lat"], hz["max_lon"]]]
            for hz in HOTZONES.values()
        ]

        subscribe_msg = json.dumps({
            "APIKey": AISSTREAM_API_KEY,
            "BoundingBoxes": bboxes,
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
        })

        while self._running:
            try:
                async with websockets.connect(url) as ws:
                    await ws.send(subscribe_msg)
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            await self._process_ais_message(msg)
                        except Exception:
                            continue
            except Exception as e:
                print(f"[AIS] Connection error: {e}. Reconnecting in 10s...")
                await asyncio.sleep(10)

    async def _process_ais_message(self, msg: dict):
        msg_type = msg.get("MessageType", "")
        meta = msg.get("MetaData", {})
        mmsi = int(meta.get("MMSI", 0))
        if not mmsi:
            return

        if msg_type == "PositionReport":
            pos = msg.get("Message", {}).get("PositionReport", {})
            lat = pos.get("Latitude", 0)
            lon = pos.get("Longitude", 0)
            sog = pos.get("Sog", 0)
            cog = pos.get("Cog", 0)

            prev = self._ships.get(mmsi)
            trail = (prev["trail"][-19:] if prev else [])
            trail.append([lon, lat])

            self._ships[mmsi] = {
                "mmsi": mmsi,
                "name": meta.get("ShipName", f"MMSI-{mmsi}").strip(),
                "lat": lat,
                "lon": lon,
                "sog": sog,
                "cog": cog,
                "type": "tanker",
                "status": "active",
                "in_hotzone": in_any_hotzone(lat, lon),
                "trail": trail,
                "last_seen": datetime.now(timezone.utc).isoformat(),
            }

        elif msg_type == "ShipStaticData":
            static = msg.get("Message", {}).get("ShipStaticData", {})
            if mmsi in self._ships:
                self._ships[mmsi]["name"] = static.get("Name", self._ships[mmsi]["name"]).strip()
                self._ships[mmsi]["type"] = static.get("Type", "unknown")

        # Broadcast update (throttled — every 10 ships)
        if len(self._ships) % 10 == 0:
            await self.on_ship_update(self.get_ships())

    # ── Serialise ─────────────────────────────────────────────────────────────

    def _serialise(self, ship: dict) -> dict:
        return {
            "mmsi": ship["mmsi"],
            "name": ship.get("name", f"MMSI-{ship['mmsi']}"),
            "lat": round(ship["lat"], 6),
            "lon": round(ship["lon"], 6),
            "sog": round(ship.get("sog", 0), 1),
            "cog": round(ship.get("cog", 0), 1),
            "type": ship.get("type", "unknown"),
            "status": ship.get("status", "active"),
            "in_hotzone": ship.get("in_hotzone"),
            "trail": ship.get("trail", [])[-15:],  # last 15 positions only
            "last_seen": ship.get("last_seen", ""),
        }
