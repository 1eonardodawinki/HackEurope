-- Maritime Sentinel — Supabase schema
-- Run this in the Supabase SQL editor

-- ── Ship positions (ring buffer — last N positions per vessel) ─────────────
CREATE TABLE IF NOT EXISTS ship_positions (
  id          BIGSERIAL PRIMARY KEY,
  mmsi        BIGINT       NOT NULL,
  name        TEXT,
  lat         DOUBLE PRECISION NOT NULL,
  lon         DOUBLE PRECISION NOT NULL,
  sog         REAL,          -- speed over ground (knots)
  cog         REAL,          -- course over ground (degrees)
  ship_type   TEXT,
  status      TEXT DEFAULT 'active',
  in_hotzone  TEXT,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ship_positions_mmsi    ON ship_positions(mmsi);
CREATE INDEX IF NOT EXISTS idx_ship_positions_time    ON ship_positions(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_ship_positions_hotzone ON ship_positions(in_hotzone) WHERE in_hotzone IS NOT NULL;

-- Auto-delete positions older than 24 hours (keep DB lean)
-- Run via pg_cron or scheduled Supabase edge function:
-- DELETE FROM ship_positions WHERE recorded_at < NOW() - INTERVAL '24 hours';


-- ── Incidents ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
  id                 TEXT PRIMARY KEY,
  incident_type      TEXT NOT NULL,          -- 'ais_dropout' | 'ship_proximity'
  mmsi               BIGINT,
  ship_name          TEXT,
  lat                DOUBLE PRECISION,
  lon                DOUBLE PRECISION,
  region             TEXT,
  severity           TEXT DEFAULT 'medium',
  duration_minutes   REAL DEFAULT 0,
  nearby_ships       JSONB,
  confidence_score   INTEGER,               -- from evaluator agent
  ai_incident_type   TEXT,                  -- evaluator's classification
  commodities_affected JSONB,              -- ["Brent Crude Oil", ...]
  evaluator_reasoning TEXT,
  occurred_at        TIMESTAMPTZ DEFAULT NOW(),
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_region ON incidents(region);
CREATE INDEX IF NOT EXISTS idx_incidents_time   ON incidents(occurred_at DESC);


-- ── Intelligence reports ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS intelligence_reports (
  id                  TEXT PRIMARY KEY DEFAULT gen_random_uuid()::TEXT,
  region              TEXT NOT NULL,
  title               TEXT,
  executive_summary   TEXT,
  threat_assessment   TEXT,
  incident_pattern    TEXT,
  chain_of_thought    TEXT,
  overall_confidence  INTEGER,
  commodity_predictions JSONB,             -- full predictions array
  supporting_evidence JSONB,              -- evidence strings
  risk_factors        JSONB,
  incident_count      INTEGER DEFAULT 0,
  critic_rounds       INTEGER DEFAULT 1,
  critic_approved     BOOLEAN DEFAULT FALSE,
  raw_report          JSONB,              -- full report as JSON
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reports_region ON intelligence_reports(region);
CREATE INDEX IF NOT EXISTS idx_reports_time   ON intelligence_reports(created_at DESC);
