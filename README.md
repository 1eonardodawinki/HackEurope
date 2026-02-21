# Maritime Sentinel

Real-time maritime intelligence platform that monitors dark vessels, detects potential incidents in geopolitical hotzones, and uses a multi-agent Claude AI pipeline to generate commodity price impact forecasts.

## Architecture

```
AISstream.io (live AIS)  ──►  FastAPI backend
       │                           │
       ▼                           ▼
 Incident Detector          WebSocket broadcast
 (AIS dropout + proximity)       │
       │                          ▼
       ▼                    React + Mapbox frontend
 Evaluator Agent (Claude)         │
 (news + commodity context)       ▼
       │                    Ship markers, hotzone overlays,
       ▼                    incident alerts, report modal
 Reporter Agent (Claude)
 (intelligence report)      Supabase
       │                    (incidents, reports, ship history)
       ▼
 Critic Agent (Claude)
 (adversarial review — up to 3 rounds)
       │
       ▼
 Final intelligence report → commodity price predictions
```

## Setup

### 1. Clone and create `.env`

```bash
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, VITE_MAPBOX_TOKEN
# Optional: AISSTREAM_API_KEY (live AIS), SUPABASE_URL + SUPABASE_SERVICE_KEY
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

## Demo mode

Without an AISstream API key, the app auto-enables demo mode:
- 30 simulated ships across the globe (real hotzone positions)
- After ~20s: a tanker goes dark in the Strait of Hormuz
- After ~45s: an unknown vessel appears nearby (STS rendezvous simulation)
- After ~70s: a Black Sea tanker goes dark
- All 3 incidents trigger the full Claude AI pipeline with a real intelligence report