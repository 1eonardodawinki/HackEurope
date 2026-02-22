# BALAGAER — Maritime Intelligence Platform

Real-time maritime dark-fleet detection and AI-powered vessel investigation platform. Monitor live AIS traffic across geopolitical hotzones, detect anomalies, and trigger deep multi-agent investigations into suspected sanctions-evading vessels.

---

## Architecture 
## Hello

```
┌─────────────────────────────────────────────────────────────────────┐
│                          LIVE MODE                                  │
│                                                                     │
│  AISstream.io WebSocket                                             │
│  (Class A + Class B vessels)                                        │
│         │                                                           │
│         ▼                                                           │
│    AIS Monitor                                                      │
│    ┌──────────────────────────────────────┐                         │
│    │  • Tracks ships in 3 hotzones        │                         │
│    │  • Detects AIS dropout (7 min dark)  │                         │
│    │  • Evicts stale ships (10 min)       │                         │
│    │  • Builds movement trails            │                         │
│    └──────────────────────────────────────┘                         │
│         │                                                           │
│         ▼                 ┌────────────────────┐                    │
│    FastAPI Backend  ──►   │  Incident Detector  │                   │
│         │                 │  (AIS dropout,      │                   │
│         │                 │   STS proximity)    │                   │
│         ▼                 └────────────────────┘                    │
│    WebSocket broadcast (2s interval)                                │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                    INVESTIGATION PIPELINE                           │
│                                                                     │
│  Operator types MMSI → POST /investigate                           │
│         │                                                           │
│         ├──► ML Model (dark fleet probability score)                │
│         │                                                           │
│         ├──► asyncio.gather() ──► News Agent      (Claude Haiku)   │
│         │                    ├──► Sanctions Agent  (Claude Haiku)   │
│         │                    └──► Geopolitical Agent (Claude Haiku) │
│         │                                                           │
│         ▼                                                           │
│    Reporter Agent (Claude Sonnet)                                   │
│    (synthesises all findings into structured report)                │
│         │                                                           │
│         ▼                                                           │
│    Critic Agent (Claude Haiku)                                      │
│    (adversarial QC review — early exit on green-light/approval)     │
│         │                                                           │
│         ▼                                                           │
│    Final Report ──► WebSocket broadcast ──► ReportModal             │
│                └──► POST /report/pdf    ──► PDF download (pdflatex) │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                       FRONTEND                                      │
│                                                                     │
│  React + Mapbox GL JS                                               │
│  ┌───────────────────────┐  ┌────────────────────────────────────┐  │
│  │  Interactive Map       │  │  Incident Panel                    │  │
│  │  • Ship markers (A+B) │  │  • Live activity log               │  │
│  │  • Movement trails    │  │  • Agent pipeline progress         │  │
│  │  • Hotzone overlays   │  │  • Investigated vessel card        │  │
│  │  • Dark ship alerts   │  │  • View / download report          │  │
│  │  • Editable zones     │  └────────────────────────────────────┘  │
│  └───────────────────────┘                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

- **Live AIS tracking** — Class A (tankers, cargo) and Class B (smaller vessels) streamed via AISstream.io with 2-second UI refresh
- **Dark fleet detection** — ships marked "dark" after 7 minutes of AIS silence; auto-evicted after 10 minutes
- **Movement trails** — visual path lines accumulate as vessels broadcast position updates
- **3 monitored hotzones** — Strait of Hormuz, Black Sea, Red Sea; fully editable polygon boundaries
- **MMSI investigation** — enter any vessel's MMSI to launch a parallel 3-agent AI investigation:
  - **News Agent** — searches for incidents, anomalies, flag state history
  - **Sanctions Agent** — checks OFAC / EU / UN exposure for vessel, owner, operator
  - **Geopolitical Agent** — assesses regional threat context and state-actor involvement
- **ML risk score** — probabilistic dark-fleet classification feeds into the report
- **Reporter → Critic loop** — Claude Sonnet drafts the intelligence report; Claude Haiku critic adversarially reviews it to improve quality control, with early exit of the loop if report is greenlit
- **PDF export** — download the final structured report as a formatted PDF
- **Demo mode** — full simulation with no live API keys required (only `ANTHROPIC_API_KEY` needed)
- **Live / Demo toggle** — switch modes at runtime from the UI

---

## Setup

### 1. Clone and configure

```bash
git clone <repo>
cd HackEurope

# Backend env
cp backend/.env.example backend/.env
# Edit backend/.env — see API Keys table below
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env        # add your VITE_MAPBOX_TOKEN
npm install
npm run dev                 # → http://localhost:5173
```

### 4. Supabase (optional persistence)

1. Create a free project at [supabase.com](https://supabase.com)
2. Run `supabase/schema.sql` in the SQL editor
3. Add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to `.env`

## API Keys

| Key | Where | Free tier |
|-----|-------|-----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | Pay-per-use |
| `VITE_MAPBOX_TOKEN` | [mapbox.com](https://mapbox.com) | 50k map loads/month |
| `AISSTREAM_API_KEY` | [aisstream.io](https://aisstream.io) | Free |
| `GFW_API_TOKEN` | [globalfishingwatch.org](https://globalfishingwatch.org/our-apis/tokens) | Free (non-commercial) |
| `SUPABASE_URL/KEY` | [supabase.com](https://supabase.com) | 500MB free |
| `NEWS_API_KEY` | [newsapi.org](https://newsapi.org) | 100 req/day free |

## How it works

1. **AIS Monitor** streams ship positions from AISstream.io (or simulates them in demo mode)
2. Ships in the **Black Sea**, **Strait of Hormuz**, and **Red Sea** are continuously tracked
3. When a ship's AIS signal drops or two ships get suspiciously close, an **incident** is flagged
4. The **Evaluator Agent** (Claude Opus 4.6) pulls news + commodity data and scores the incident (0–100%)
5. When ≥3 incidents occur in a region within 24h, the **Reporter Agent** generates an intelligence report
6. The **Critic Agent** adversarially reviews the report (up to 3 rounds) until it approves
7. The final report shows **commodity price impact predictions** with confidence scores

## Quick start (demo mode)

Demo mode runs entirely without live API keys — only `ANTHROPIC_API_KEY` is required.

**1. Start the backend**

```bash
cd backend

# Windows
python -m venv .venv && .venv\Scripts\activate
# macOS / Linux
python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
cp .env.example .env        # add VITE_MAPBOX_TOKEN
npm install
npm run dev                 # → http://localhost:5173
```

### 4. Supabase (optional — for incident persistence)

1. Create a free project at [supabase.com](https://supabase.com)
2. Run `supabase/schema.sql` in the SQL editor
3. Add `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` to `backend/.env`

---

## API Keys

| Key | Purpose | Where to get | Free tier |
|-----|---------|--------------|-----------|
| `ANTHROPIC_API_KEY` | All Claude agents | [console.anthropic.com](https://console.anthropic.com) | Pay-per-use |
| `VITE_MAPBOX_TOKEN` | Interactive map | [mapbox.com](https://mapbox.com) | 50k loads/month |
| `AISSTREAM_API_KEY` | Live AIS feed | [aisstream.io](https://aisstream.io) | Free |
| `NEWS_API_KEY` | News Agent searches | [newsapi.org](https://newsapi.org) | 100 req/day free |
| `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` | Incident persistence | [supabase.com](https://supabase.com) | 500 MB free |

> **Minimum to run demo mode:** only `ANTHROPIC_API_KEY` + `VITE_MAPBOX_TOKEN` are required.

---

## Quick start (demo mode)

Demo mode activates automatically when `AISSTREAM_API_KEY` is absent. You can also force it with `DEMO_MODE=true` in `backend/.env`.

**1. Start the backend**

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload
```

**2. Start the frontend** (new terminal)

```bash
cd frontend
npm install && npm run dev
```

**3. Open** [http://localhost:5173](http://localhost:5173)

---

### Demo timeline

| Time | Event | Region |
|------|-------|--------|
| 0 s | Backend starts, 30 ships initialised across all hotzones | — |
| 5 s | Ship positions begin streaming to the map | — |
| 20 s | **PERSIAN STAR** AIS signal lost — ship goes dark | Strait of Hormuz |
| 45 s | **UNKNOWN VESSEL** appears 0.3 NM from dark ship (STS rendezvous) | Strait of Hormuz |
| 70 s | **FALCON SPIRIT** AIS signal lost | Strait of Hormuz |
| ~75 s | Incident threshold reached — investigation pipeline fires automatically | — |
| ~80–120 s | Reporter drafts report; Critic reviews (exits early if approved) | — |
| ~120 s | Final intelligence report broadcast → report modal opens | — |
| 95 s | **ODESSA SPIRIT** goes dark — fresh Black Sea incident chain begins | Black Sea |

---

## Manual investigation (live or demo)

1. Type a 9-digit MMSI into the search box in the header
2. Click **INVESTIGATE** (or press Enter)
3. Watch the Incident Panel — three agents run concurrently, progress updates stream in real time
4. When the report is ready the modal opens automatically; click **Download PDF** for a portable copy

---

## Project structure

```
HackEurope/
├── backend/
│   ├── main.py                    # FastAPI app, WebSocket, REST endpoints
│   ├── config.py                  # API keys, hotzone definitions, thresholds
│   ├── ais_monitor.py             # AISstream WebSocket client + demo simulator
│   ├── incident_detector.py       # AIS dropout + proximity detection
│   ├── ml_model.py                # Dark-fleet probability stub (ML team replaces internals)
│   ├── report_renderer.py         # ReportLab PDF generation
│   ├── database.py                # Supabase REST client (optional)
│   ├── agents/
│   │   ├── investigation_agents.py  # News / Sanctions / Geopolitical agents + orchestrator
│   │   ├── reporter_agent.py        # Reporter + Critic loop (region & investigation reports)
│   │   └── evaluator_agent.py       # Incident evaluator (demo mode)
│   └── data_fetchers/
│       ├── news_fetcher.py          # NewsAPI search (used by investigation agents)
│       └── commodity_fetcher.py     # Alpha Vantage commodity prices
└── frontend/
    └── src/
        ├── App.jsx                  # Root — state, WebSocket wiring, MMSI search
        ├── components/
        │   ├── Map.jsx              # Mapbox GL map, ship markers, trails, hotzone polygons
        │   ├── IncidentPanel.jsx    # Activity log, agent progress, vessel card
        │   └── ReportModal.jsx      # Intelligence report viewer + PDF download
        └── hooks/
            └── useWebSocket.js      # WebSocket connection + message dispatcher
```
