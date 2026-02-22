import { useState, useCallback } from 'react'
import Map from './components/Map.jsx'
import IncidentPanel from './components/IncidentPanel.jsx'
import ReportModal from './components/ReportModal.jsx'
import { useWebSocket } from './hooks/useWebSocket.js'

export default function App() {
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
  const [mmsiInput, setMmsiInput] = useState('')
  const [investigating, setInvestigating] = useState(false)
  const [investigatedVessel, setInvestigatedVessel] = useState(null)

  const handleZoneChange = useCallback((name, geo) => {
    setZoneOverrides(prev => ({ ...prev, [name]: geo }))
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
      if (data.vessel) {
        setSelectedShip(data.vessel)
        setInvestigatedVessel(data.vessel)
      }
    },
    onReport: (data) => {
      setReport(data)
      setShowReport(true)
      setInvestigating(false)
      addLog({ kind: 'report', text: `Report ready: "${data.title || 'Intelligence Report'}" — ${data.overall_confidence || '?'}% confidence` })
    },
  })

  const submitInvestigation = async () => {
    const mmsi = mmsiInput.trim()
    if (!mmsi || investigating) return
    setInvestigating(true)

    // Immediately highlight the vessel on the map if it's in the current AIS feed
    const vessel = ships.find(s => String(s.mmsi) === mmsi)
    if (vessel) {
      setSelectedShip(vessel)
      setInvestigatedVessel(vessel)
    } else {
      setInvestigatedVessel({ mmsi, name: 'Unknown Vessel', notFound: true })
    }

    addLog({ kind: 'system', text: `Investigation launched for MMSI ${mmsi}` })
    try {
      await fetch('http://localhost:8000/investigate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mmsi }),
      })
    } catch {
      setInvestigating(false)
      setInvestigatedVessel(null)
      addLog({ kind: 'error', text: `Failed to reach backend for MMSI ${mmsi}` })
    }
  }

  const abortInvestigation = async () => {
    try {
      await fetch('http://localhost:8000/investigate/abort', { method: 'POST' })
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
      await fetch('http://localhost:8000/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ demo: toDemo }),
      })
    } catch {
      setModeSwitching(false)
    }
  }

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
            hotzones={hotzones}
            incidents={[]}
            selectedShip={selectedShip}
            onSelectShip={setSelectedShip}
            editZones={editZones}
            zoneOverrides={zoneOverrides}
            onZoneChange={handleZoneChange}
          />
        </div>

        <IncidentPanel
          investigatedVessel={investigatedVessel}
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
          background: investigating ? 'rgba(0,229,255,0.08)' : 'transparent',
          border: `1px solid ${investigating ? 'var(--accent)' : 'var(--border)'}`,
          color: investigating ? 'var(--accent)' : 'var(--text3)',
          fontSize: 9, letterSpacing: 2, fontFamily: 'inherit',
          padding: '4px 10px', cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled && !investigating ? 0.4 : 1,
          transition: 'all 0.15s',
        }}
      >
        {investigating ? 'RUNNING' : 'INVESTIGATE'}
      </button>
    </div>
  )
}
