import { useState, useCallback, useRef } from 'react'
import Map from './components/Map.jsx'
import IncidentPanel from './components/IncidentPanel.jsx'
import ReportModal from './components/ReportModal.jsx'
import { useWebSocket } from './hooks/useWebSocket.js'

export default function App() {
  const [ships, setShips] = useState([])
  const [hotzones, setHotzones] = useState({})
  const [incidents, setIncidents] = useState([])
  const [evaluations, setEvaluations] = useState([])
  const [agentStatus, setAgentStatus] = useState({ stage: 'idle', message: 'Connecting...' })
  const [thresholds, setThresholds] = useState({})
  const [report, setReport] = useState(null)
  const [showReport, setShowReport] = useState(false)
  const [connected, setConnected] = useState(false)
  const [demoMode, setDemoMode] = useState(false)
  const [hasLiveKey, setHasLiveKey] = useState(false)
  const [modeSwitching, setModeSwitching] = useState(false)
  const [selectedShip, setSelectedShip] = useState(null)
  const [editZones, setEditZones] = useState(false)
  const [zoneOverrides, setZoneOverrides] = useState({})

  const handleZoneChange = useCallback((name, geo) => {
    setZoneOverrides(prev => ({ ...prev, [name]: geo }))
  }, [])

  const incidentIds = useRef(new Set())

  const addIncident = useCallback((incident) => {
    if (incidentIds.current.has(incident.id)) return
    incidentIds.current.add(incident.id)
    setIncidents(prev => [incident, ...prev].slice(0, 50))
  }, [])

  useWebSocket({
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
    onInit: (data) => {
      setShips(data.ships || [])
      setHotzones(data.hotzones || {})
      setDemoMode(!!data.demo_mode)
      setHasLiveKey(!!data.has_live_key)
    },
    onModeChange: (data) => {
      setDemoMode(!!data.demo_mode)
      setHasLiveKey(!!data.has_live_key)
      setModeSwitching(false)
      // Reset transient state for the new session
      setShips([])
      setIncidents([])
      setEvaluations([])
      setThresholds({})
      setReport(null)
      setShowReport(false)
      setAgentStatus({ stage: 'idle', message: 'Monitoring...' })
      incidentIds.current.clear()
    },
    onShips: (data) => setShips(data),
    onIncident: (data) => addIncident(data),
    onEvaluation: (data) => {
      setEvaluations(prev => [data, ...prev].slice(0, 100))
      setIncidents(prev => prev.map(inc =>
        inc.id === data.incident_id
          ? { ...inc, confidence_score: data.confidence_score, incident_type: data.incident_type, commodities_affected: data.commodities_affected }
          : inc
      ))
    },
    onAgentStatus: (data) => setAgentStatus(data),
    onThresholdUpdate: (data) => {
      setThresholds(prev => ({ ...prev, [data.region]: data }))
    },
    onReport: (data) => {
      setReport(data)
      setShowReport(true)
    },
  })

  const switchMode = async (toDemo) => {
    if (modeSwitching) return
    setModeSwitching(true)
    try {
      await fetch('http://localhost:8000/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ demo: toDemo }),
      })
    } catch {
      setModeSwitching(false)
    }
  }

  const totalIncidents = incidents.length
  const hotzoneShips = ships.filter(s => s.in_hotzone).length
  const darkShips = ships.filter(s => s.status === 'dark').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)' }}>

      {/* ── Header ── */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>BALAGAER</span>
          <span style={styles.logoSub}>Intelligence Monitoring Platform</span>
        </div>

        <div style={styles.headerStats}>
          <Stat label="VESSELS" value={ships.length} />
          <Stat label="IN ZONE" value={hotzoneShips} color="var(--warning)" />
          <Stat label="DARK" value={darkShips} color="var(--danger)" />
          <Stat label="INCIDENTS" value={totalIncidents} color={totalIncidents > 0 ? 'var(--danger)' : 'var(--text)'} />
        </div>

        <div style={styles.headerRight}>
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
            hotzones={hotzones}
            incidents={incidents}
            selectedShip={selectedShip}
            onSelectShip={setSelectedShip}
            editZones={editZones}
            zoneOverrides={zoneOverrides}
            onZoneChange={handleZoneChange}
          />
        </div>

        <IncidentPanel
          incidents={incidents}
          thresholds={thresholds}
          agentStatus={agentStatus}
          hotzones={hotzones}
          onOpenReport={() => setShowReport(true)}
          hasReport={!!report}
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
  // Switching TO demo: always allowed. Switching TO live: only if API key exists.
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
  const stageColors = { evaluator: 'var(--accent)', reporter: 'var(--green)', critic: 'var(--warning)' }
  const color = stageColors[status.stage] || 'var(--text3)'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      padding: '3px 10px', border: `1px solid ${color}22`,
      background: `${color}08`,
    }}>
      <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, animation: 'pulse-dot 1s infinite' }} />
      <span style={{ fontSize: 9, color, letterSpacing: 1.5, textTransform: 'uppercase' }}>
        {status.stage}
      </span>
    </div>
  )
}

const styles = {
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 24px', height: 48,
    background: 'var(--bg)',
    borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  },
  headerLeft: { display: 'flex', alignItems: 'baseline', gap: 14 },
  logo: {
    fontSize: 13, fontWeight: 600, color: 'var(--text)',
    letterSpacing: 3, textTransform: 'uppercase',
  },
  logoSub: { fontSize: 10, color: 'var(--text3)', letterSpacing: 1 },
  headerStats: { display: 'flex', gap: 32 },
  stat: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  headerRight: { display: 'flex', alignItems: 'center', gap: 12 },
  liveIndicator: { display: 'flex', alignItems: 'center', gap: 7 },
  editZonesBtn: {
    background: 'transparent', border: '1px solid', cursor: 'pointer',
    fontSize: 9, letterSpacing: 2, fontFamily: 'inherit',
    padding: '4px 10px', transition: 'color 0.15s, border-color 0.15s',
  },
}
