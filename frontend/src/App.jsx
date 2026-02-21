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
  const [selectedShip, setSelectedShip] = useState(null)

  // Deduplicate incidents by id
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
    },

    onShips: (data) => setShips(data),

    onIncident: (data) => addIncident(data),

    onEvaluation: (data) => {
      setEvaluations(prev => [data, ...prev].slice(0, 100))
      // Update the matching incident with confidence info
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

  const totalIncidents = incidents.length
  const hotzoneShips = ships.filter(s => s.in_hotzone).length
  const darkShips = ships.filter(s => s.status === 'dark').length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg)' }}>

      {/* ── Top Header Bar ── */}
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.logo}>⚓ MARITIME SENTINEL</span>
          <span style={styles.subtitle}>Intelligence Monitoring Platform</span>
        </div>

        <div style={styles.headerStats}>
          <Stat label="VESSELS" value={ships.length} color="var(--accent)" />
          <Stat label="IN ZONE" value={hotzoneShips} color="var(--warning)" />
          <Stat label="DARK" value={darkShips} color="var(--danger)" />
          <Stat label="INCIDENTS" value={totalIncidents} color="var(--danger)" />
        </div>

        <div style={styles.headerRight}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              width: 8, height: 8, borderRadius: '50%',
              background: connected ? 'var(--green)' : 'var(--danger)',
              boxShadow: connected ? 'var(--glow-green)' : 'var(--glow-danger)',
              animation: 'pulse-dot 2s infinite'
            }} />
            <span style={{ fontSize: 11, color: 'var(--text2)', letterSpacing: 1 }}>
              {connected ? 'LIVE' : 'RECONNECTING'}
            </span>
          </div>
          {agentStatus.stage !== 'idle' && agentStatus.stage !== 'critic_result' && (
            <AgentBadge status={agentStatus} />
          )}
        </div>
      </header>

      {/* ── Main Layout ── */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Map */}
        <div style={{ flex: 1, position: 'relative' }}>
          <Map
            ships={ships}
            hotzones={hotzones}
            incidents={incidents}
            selectedShip={selectedShip}
            onSelectShip={setSelectedShip}
          />
        </div>

        {/* Right sidebar */}
        <IncidentPanel
          incidents={incidents}
          thresholds={thresholds}
          agentStatus={agentStatus}
          hotzones={hotzones}
          onOpenReport={() => setShowReport(true)}
          hasReport={!!report}
        />
      </div>

      {/* Intelligence Report Modal */}
      {showReport && report && (
        <ReportModal report={report} onClose={() => setShowReport(false)} />
      )}
    </div>
  )
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.stat}>
      <span style={{ ...styles.statValue, color }}>{value}</span>
      <span style={styles.statLabel}>{label}</span>
    </div>
  )
}

function AgentBadge({ status }) {
  const stageColors = { evaluator: 'var(--accent)', reporter: 'var(--green)', critic: 'var(--warning)' }
  const color = stageColors[status.stage] || 'var(--text2)'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px',
      background: 'rgba(0,0,0,0.4)', border: `1px solid ${color}`, borderRadius: 4 }}>
      <div style={{ width: 6, height: 6, borderRadius: '50%', background: color, animation: 'pulse-dot 1s infinite' }} />
      <span style={{ fontSize: 10, color, letterSpacing: 0.5, textTransform: 'uppercase' }}>
        {status.stage} running
      </span>
    </div>
  )
}

const styles = {
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 20px', height: 52,
    background: 'var(--panel)', borderBottom: '1px solid var(--border)',
    flexShrink: 0,
  },
  headerLeft: { display: 'flex', alignItems: 'baseline', gap: 12 },
  logo: { fontSize: 16, fontWeight: 700, color: 'var(--accent)', letterSpacing: 2, textTransform: 'uppercase' },
  subtitle: { fontSize: 10, color: 'var(--text3)', letterSpacing: 1 },
  headerStats: { display: 'flex', gap: 28 },
  stat: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 },
  statValue: { fontSize: 20, fontWeight: 700, lineHeight: 1 },
  statLabel: { fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5 },
  headerRight: { display: 'flex', alignItems: 'center', gap: 16 },
}
