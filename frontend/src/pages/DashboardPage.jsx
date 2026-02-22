import { useState, useCallback, useRef } from 'react'
import Map from '../components/Map.jsx'
import IncidentPanel from '../components/IncidentPanel.jsx'
import ReportModal from '../components/ReportModal.jsx'
import { useWebSocket } from '../hooks/useWebSocket.js'

const API = import.meta.env.PROD ? '' : 'http://localhost:8000'
const TRACK_API = import.meta.env.PROD ? '' : 'http://localhost:8001'

export default function DashboardPage({ onHome }) {
  const [ships, setShips] = useState([])
  const [hotzones, setHotzones] = useState({})
  const [agentStatus, setAgentStatus] = useState({ stage: 'idle', message: 'Connecting...' })
  const [report, setReport] = useState(null)
  const [showReport, setShowReport] = useState(false)
  const [connected, setConnected] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  const [hasLiveKey, setHasLiveKey] = useState(false)
  const [modeSwitching, setModeSwitching] = useState(false)
  const [selectedShip, setSelectedShip] = useState(null)
  const [editZones, setEditZones] = useState(false)
  const [zoneOverrides, setZoneOverrides] = useState({})
  const [deletedZones, setDeletedZones] = useState(new Set())
  const [customZones, setCustomZones] = useState({})
  const zoneCountRef = useRef(0)
  const [mmsiInput, setMmsiInput] = useState('')
  const [investigating, setInvestigating] = useState(false)
  const [, setInvestigatedVessel] = useState(null)
  const [gfwPath, setGfwPath] = useState(null)
  const [unmatchedPoints, setUnmatchedPoints] = useState(null)

  const handleZoneChange = useCallback((name, geo) => {
    setZoneOverrides(prev => ({ ...prev, [name]: geo }))
  }, [])

  const handleDeleteZone = useCallback((name) => {
    setDeletedZones(prev => new Set([...prev, name]))
    setCustomZones(prev => { const next = { ...prev }; delete next[name]; return next })
  }, [])

  const handleAddZone = useCallback(({ centerLon, centerLat }) => {
    zoneCountRef.current += 1
    const name = `Zone ${zoneCountRef.current}`
    const r = 5
    setCustomZones(prev => ({
      ...prev,
      [name]: { min_lat: centerLat - r, max_lat: centerLat + r, min_lon: centerLon - r, max_lon: centerLon + r, color: '#ff6b00', description: '', commodities: [] },
    }))
  }, [])

  const [logs, setLogs] = useState([])

  const addLog = useCallback((entry) => {
    const ts = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    setLogs(prev => [{ ...entry, ts }, ...prev].slice(0, 300))
  }, [])

  useWebSocket({
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
    onInit: (data) => {
      setShips(data.ships || [])
      setHotzones(data.hotzones || {})
      setDemoMode(!!data.demo_mode)
      setHasLiveKey(!!data.has_live_key)
      setModeSwitching(false)
    },
    onModeChange: (data) => {
      setDemoMode(!!data.demo_mode)
      setHasLiveKey(!!data.has_live_key)
      setModeSwitching(false)
      setShips([])
      setReport(null)
      setShowReport(false)
      setAgentStatus({ stage: 'idle', message: 'Monitoring...' })
      setLogs([])
      setInvestigatedVessel(null)
      setGfwPath(null)
      setUnmatchedPoints(null)
      setInvestigating(false)
      addLog({ kind: 'system', text: `Switched to ${data.demo_mode ? 'DEMO' : 'LIVE'} mode` })
    },
    onShips: (data) => setShips(data),
    onAgentStatus: (data) => {
      setAgentStatus(data)
      if (data.stage === 'aborted') {
        setInvestigating(false)
        setAgentStatus({ stage: 'idle', message: '' })
        addLog({ kind: 'system', text: `Investigation aborted` })
      } else if (data.stage === 'error') {
        setInvestigating(false)
        addLog({ kind: 'error', text: `Pipeline error: ${data.message}` })
      } else if (data.stage === 'critic_result') {
        addLog({ kind: 'critic', text: `Critic round ${data.round}: ${data.approved ? '✓ APPROVED' : '✗ REVISE'} (quality ${data.quality_score}/100)`, approved: data.approved })
      } else if (data.stage !== 'idle' && data.stage !== 'reporter_stream') {
        addLog({ kind: 'agent', text: data.message || data.stage, stage: data.stage, round: data.round })
      }
    },
    onInvestigationStart: (data) => {
      // Backend confirmed vessel location — update map highlight with latest AIS data
      setGfwPath(null)  // Clear previous path when new investigation starts
      setUnmatchedPoints(null)
      if (data.vessel) {
        setSelectedShip(data.vessel)
        setInvestigatedVessel(data.vessel)
      }
    },
    onGfwPath: (data) => {
      setGfwPath(data)
      // Enrich investigated vessel with GFW metadata (name, type) when available
      if (data?.metadata) {
        setInvestigatedVessel(prev => prev && String(prev.mmsi) === String(data.mmsi) ? {
          ...prev,
          name: data.metadata.name || prev.name,
          type: data.metadata.ship_type || prev.type,
        } : prev)
      }
    },
    onUnmatchedPoints: (data) => {
      setUnmatchedPoints(data)
    },
    onReport: (data) => {
      setReport(data)
      setShowReport(true)
      setInvestigating(false)
      addLog({ kind: 'report', text: `Report ready: "${data.title || 'Intelligence Report'}" — ${data.overall_confidence || '?'}% confidence` })
    },
  })

  const trackShip = async (mmsiOverride) => {
    const mmsi = mmsiOverride != null ? String(mmsiOverride).trim() : mmsiInput.trim()
    if (!mmsi) return
    if (mmsiOverride != null) setMmsiInput(String(mmsiOverride))
    setGfwPath(null)
    setUnmatchedPoints(null)
    const vessel = ships.find((s) => String(s.mmsi) === mmsi)
    if (vessel) {
      setSelectedShip(vessel)
      setInvestigatedVessel(vessel)
    } else {
      setInvestigatedVessel({ mmsi, name: 'Loading…', notFound: true })
    }
    const normalizeBackendPath = (data) => {
      if (!data) return null
      const path = (data.path || []).map((p) => ({ lat: p.lat, lon: p.lon }))
      return {
        mmsi,
        path,
        path_segments: data.path_segments || [path],
        metadata: data.metadata || {},
        error: data.error || null,
      }
    }

    try {
      // Call the track microservice (port 8001) — maritime-routed, no land crossings
      const today = new Date()
      const sixMonthsAgo = new Date(today)
      sixMonthsAgo.setMonth(today.getMonth() - 6)
      const start = sixMonthsAgo.toISOString().slice(0, 10)
      const end = today.toISOString().slice(0, 10)

      const r = await fetch(
        `${TRACK_API}/track?mmsi=${encodeURIComponent(mmsi)}&start=${start}&end=${end}`
      )
      const data = await r.json()

      if (data?.detail) throw new Error(data.detail)

      // Normalize to the shape Map.jsx already understands
      const path = (data.points || []).map((p) => ({ lat: p.lat, lon: p.lon }))
      const gfwData = {
        path,
        path_segments: [path],
        metadata: {
          name: data.name,
          ship_type: data.ship_type,
          flag: data.flag,
          point_count: data.point_count,
          time_range: data.time_range,
          data_source: 'maritime_routed',
        },
      }
      setGfwPath(gfwData)
      if (data.name) {
        setInvestigatedVessel((prev) =>
          prev && String(prev.mmsi) === mmsi
            ? { ...prev, name: data.name, type: data.ship_type }
            : prev
        )
      }
    } catch {
      // Fallback to backend GFW path endpoint when track microservice is unavailable.
      try {
        const r = await fetch(`${API}/gfw-path?mmsi=${encodeURIComponent(mmsi)}`)
        const data = await r.json()
        const normalized = normalizeBackendPath(data)
        setGfwPath(normalized || { mmsi, error: 'Invalid path response', path: [], metadata: {} })
        if (data?.metadata?.name) {
          setInvestigatedVessel((prev) =>
            prev && String(prev.mmsi) === mmsi
              ? { ...prev, name: data.metadata.name, type: data.metadata.ship_type }
              : prev
          )
        }
      } catch (err2) {
        setGfwPath({ mmsi, error: String(err2), path: [], metadata: {} })
      }
    }

    try {
      const r = await fetch(`${API}/historical-unmatched?mmsi=${encodeURIComponent(mmsi)}`)
      const data = await r.json()
      setUnmatchedPoints(data)
    } catch (err) {
      setUnmatchedPoints({
        mmsi,
        error: String(err),
        points: [],
        metadata: { point_count: 0, data_source: 'historical_unmatched' },
      })
    }
  }

  const submitInvestigation = async () => {
    const mmsi = mmsiInput.trim()
    if (!mmsi || investigating) return
    setInvestigating(true)

    // Immediately highlight the vessel on the map if it's in the current AIS feed
    setGfwPath(null)  // Clear path when starting new investigation
    setUnmatchedPoints(null)
    const vessel = ships.find(s => String(s.mmsi) === mmsi)
    if (vessel) {
      setSelectedShip(vessel)
      setInvestigatedVessel(vessel)
    } else {
      setInvestigatedVessel({ mmsi, name: 'Unknown Vessel', notFound: true })
    }

    addLog({ kind: 'system', text: `Investigation launched for MMSI ${mmsi}` })
    try {
      await fetch(`${API}/investigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mmsi }),
      })
    } catch {
      setInvestigating(false)
      setInvestigatedVessel(null)
      addLog({ kind: 'error', text: `Failed to reach backend for MMSI ${mmsi}` })
    }

    try {
      const r = await fetch(`${API}/historical-unmatched?mmsi=${encodeURIComponent(mmsi)}`)
      const data = await r.json()
      setUnmatchedPoints(data)
    } catch (err) {
      setUnmatchedPoints({
        mmsi,
        error: String(err),
        points: [],
        metadata: { point_count: 0, data_source: 'historical_unmatched' },
      })
    }
  }

  const abortInvestigation = async () => {
    try {
      await fetch(`${API}/investigate/abort`, { method: 'POST' })
    } catch {
      // Backend unreachable — reset state client-side anyway
    }
    setInvestigating(false)
    setAgentStatus({ stage: 'idle', message: '' })
    addLog({ kind: 'system', text: 'Investigation aborted' })
  }

  const switchMode = async (toDemo) => {
    if (modeSwitching) return
    setModeSwitching(true)
    try {
      await fetch(`${API}/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ demo: toDemo }),
      })
    } catch {
      setModeSwitching(false)
    }
  }

  const visibleHotzones = {
    ...Object.fromEntries(Object.entries(hotzones).filter(([name]) => !deletedZones.has(name))),
    ...customZones,
  }
  const hotzoneShips = ships.filter(s => s.in_hotzone).length
  const darkShips = ships.filter(s => s.status === 'dark').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)' }}>

      {/* ── Header ── */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={{ ...styles.logo, cursor: onHome ? 'pointer' : 'default' }} onClick={onHome}>PELAGOS</span>
        </div>

        <div style={styles.headerStats}>
          <Stat label="VESSELS" value={ships.length} />
          <Stat label="IN ZONE" value={hotzoneShips} color="var(--warning)" />
          <Stat label="DARK" value={darkShips} color="var(--danger)" />
        </div>

        <div style={styles.headerRight}>
          <MmsiSearch
            value={mmsiInput}
            onChange={setMmsiInput}
            onSubmit={submitInvestigation}
            disabled={investigating || !connected}
            investigating={investigating}
          />
          <div style={styles.headerDivider} />
          <ModeIndicator
            connected={connected}
            demoMode={demoMode}
            hasLiveKey={hasLiveKey}
            switching={modeSwitching}
            onSwitch={switchMode}
          />
          {agentStatus.stage !== 'idle' && agentStatus.stage !== 'critic_result' && (
            <AgentBadge status={agentStatus} />
          )}
          <button
            style={{
              ...styles.editZonesBtn,
              borderColor: editZones ? 'rgba(255,255,255,0.3)' : 'var(--border)',
              color: editZones ? 'var(--text)' : 'var(--text3)',
            }}
            onClick={() => setEditZones(v => !v)}
          >
            {editZones ? 'DONE' : 'EDIT ZONES'}
          </button>
        </div>
      </header>

      {/* ── Body ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <Map
            ships={ships}
            hotzones={visibleHotzones}
            incidents={[]}
            selectedShip={selectedShip}
            onSelectShip={(ship) => {
              setSelectedShip(ship)
              if (!ship) { setGfwPath(null); setUnmatchedPoints(null) }
            }}
            editZones={editZones}
            zoneOverrides={zoneOverrides}
            onZoneChange={handleZoneChange}
            onDeleteZone={handleDeleteZone}
            onAddZone={handleAddZone}
            gfwPath={gfwPath}
            unmatchedPoints={unmatchedPoints}
            onTrackByMmsi={(mmsi) => trackShip(mmsi)}
          />
        </div>

        <IncidentPanel
          investigating={investigating}
          agentStatus={agentStatus}
          logs={logs}
          onOpenReport={() => setShowReport(true)}
          hasReport={!!report}
          onAbort={abortInvestigation}
        />
      </div>

      {showReport && report && (
        <ReportModal report={report} onClose={() => setShowReport(false)} />
      )}
    </div>
  )
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.stat}>
      <span style={{ fontSize: 22, fontWeight: 300, color: color || 'var(--text)', lineHeight: 1, letterSpacing: -0.5 }}>
        {value}
      </span>
      <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 2, marginTop: 2 }}>{label}</span>
    </div>
  )
}

function ModeIndicator({ connected, demoMode, hasLiveKey, switching, onSwitch }) {
  const dotColor = !connected ? 'var(--danger)' : demoMode ? 'var(--danger)' : 'var(--green)'
  const label = !connected ? 'RECONNECTING' : switching ? '...' : demoMode ? 'DEMO' : 'LIVE'
  const labelColor = !connected ? 'var(--danger)' : demoMode ? 'var(--danger)' : 'var(--text2)'
  const canToggle = connected && !switching && (demoMode ? hasLiveKey : true)
  const toggleTarget = demoMode ? 'LIVE' : 'DEMO'
  const toggleTitle = demoMode && !hasLiveKey
    ? 'No AISSTREAM_API_KEY configured'
    : `Switch to ${toggleTarget}`

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
        <div style={{
          width: 6, height: 6, borderRadius: '50%',
          background: dotColor,
          animation: 'pulse-dot 2s infinite',
        }} />
        <span style={{ fontSize: 10, color: labelColor, letterSpacing: 1.5 }}>{label}</span>
      </div>
      {connected && (
        <button
          onClick={() => onSwitch(!demoMode)}
          disabled={!canToggle}
          title={toggleTitle}
          style={{
            fontSize: 9, letterSpacing: 1.5, padding: '2px 8px',
            background: 'transparent',
            border: '1px solid var(--border)',
            color: 'var(--text3)',
            cursor: canToggle ? 'pointer' : 'not-allowed',
            opacity: canToggle ? 1 : 0.4,
            fontFamily: 'inherit',
            textTransform: 'uppercase',
          }}
        >
          {toggleTarget}
        </button>
      )}
    </div>
  )
}

function AgentBadge({ status }) {
  const stageColors = { evaluator: 'var(--accent)', reporter: 'var(--green)', reporter_stream: 'var(--green)', critic: 'var(--warning)' }
  const color = stageColors[status.stage] || 'var(--text3)'
  const label = status.stage === 'reporter_stream' ? 'REPORTER' : status.stage
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', border: `1px solid ${color}22`,
      background: `${color}08`,
    }}>
      <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, animation: 'pulse-dot 1s infinite' }} />
      <span style={{ fontSize: 9, color, letterSpacing: 1.5, textTransform: 'uppercase' }}>
        {label}
      </span>
    </div>
  )
}

const styles = {
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 24px', height: 64,
    background: 'var(--bg)',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  },
  headerLeft: { display: 'flex', alignItems: 'baseline', gap: 14 },
  logo: {
    fontSize: 18, fontWeight: 700, color: 'var(--text)',
    letterSpacing: 4, textTransform: 'uppercase',
    fontFamily: '"Barlow Condensed", "Barlow", system-ui, sans-serif',
  },
  logoSub: { fontSize: 10, color: 'var(--text3)', letterSpacing: 1 },
  headerStats: { display: 'flex', gap: 32 },
  stat: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  headerDivider: { width: 1, height: 20, background: 'var(--border)', flexShrink: 0 },
  editZonesBtn: {
    background: 'transparent', border: '1px solid', cursor: 'pointer',
    fontSize: 9, letterSpacing: 2, fontFamily: 'inherit',
    padding: '4px 10px', transition: 'color 0.15s, border-color 0.15s',
  },
}

function MmsiSearch({ value, onChange, onSubmit, disabled, investigating }) {
  const handleKey = (e) => { if (e.key === 'Enter') onSubmit() }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <input
        type="text"
        placeholder="MMSI number"
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKey}
        maxLength={9}
        style={{
          background: 'transparent',
          border: '1px solid var(--border)',
          color: 'var(--text)',
          fontSize: 10,
          fontFamily: 'inherit',
          letterSpacing: 1,
          padding: '3px 8px',
          width: 100,
          outline: 'none',
        }}
      />
      <button
        onClick={onSubmit}
        disabled={disabled || !value.trim()}
        style={{
          background: investigating ? 'rgba(0,229,255,0.08)' : '#fff',
          border: `1px solid ${investigating ? 'var(--accent)' : '#fff'}`,
          color: investigating ? 'var(--accent)' : '#000',
          fontSize: 9, letterSpacing: 2, fontFamily: 'inherit', fontWeight: 700,
          padding: '5px 12px', cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled && !investigating ? 0.35 : 1,
          transition: 'all 0.15s',
        }}
      >
        {investigating ? 'RUNNING' : 'INVESTIGATE'}
      </button>
    </div>
  )
}
