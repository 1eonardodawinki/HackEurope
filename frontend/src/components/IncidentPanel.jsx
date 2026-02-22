import { useState, useEffect } from 'react'

const TAB_LABELS = { agents: 'AGENTS', log: 'LOG' }

export default function IncidentPanel({
  investigating, agentStatus, logs, onOpenReport, hasReport, onAbort
}) {
  const [activeTab, setActiveTab] = useState('agents')

  // Switch to AGENTS tab when the pipeline becomes active
  useEffect(() => {
    if (agentStatus.stage !== 'idle' && agentStatus.stage !== 'critic_result') {
      setActiveTab('agents')
    }
  }, [agentStatus.stage])

  return (
    <div style={styles.panel}>
      {/* Tabs */}
      <div style={styles.tabs}>
        {Object.entries(TAB_LABELS).map(([tab, label]) => (
          <button key={tab}
            style={{ ...styles.tab, ...(activeTab === tab ? styles.tabActive : {}) }}
            onClick={() => setActiveTab(tab)}>
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'agents' && <AgentsTab agentStatus={agentStatus} />}
      {activeTab === 'log'    && <LogTab logs={logs || []} onOpenReport={onOpenReport} hasReport={hasReport} />}

      {investigating && (
        <button style={styles.abortBtn} onClick={onAbort}>
          ABORT INVESTIGATION
        </button>
      )}
      {hasReport && !investigating && (
        <button style={styles.reportCta} onClick={onOpenReport}>
          VIEW INTELLIGENCE REPORT
        </button>
      )}
    </div>
  )
}

function AgentsTab({ agentStatus }) {
  const stages = [
    { id: 'news_agent',         label: 'News Agent',        desc: 'Searches vessel news, incidents & AIS anomalies' },
    { id: 'sanctions_agent',    label: 'Sanctions Agent',   desc: 'Checks OFAC / EU / UN sanctions exposure' },
    { id: 'geopolitical_agent', label: 'Geopolitical Agent',desc: 'Assesses regional threat & state-actor context' },
    { id: 'reporter',           label: 'Reporter',          desc: 'Synthesises findings into an intelligence report' },
    { id: 'critic',             label: 'Critic',            desc: 'Adversarial review — exits early when approved' },
  ]

  return (
    <div style={styles.scrollArea}>
      <div style={{ fontSize: 10, color: 'var(--text3)', letterSpacing: 0.5, marginBottom: 16, lineHeight: 1.6 }}>
        Multi-agent intelligence pipeline
      </div>

      {stages.map(stage => {
        const isActive = agentStatus.stage === stage.id ||
          (stage.id === 'reporter' && agentStatus.stage === 'reporter_stream') ||
          (stage.id === 'news_agent' && agentStatus.stage === 'investigation') ||
          (stage.id === 'sanctions_agent' && agentStatus.stage === 'investigation') ||
          (stage.id === 'geopolitical_agent' && agentStatus.stage === 'investigation')
        return (
          <div key={stage.id} style={{
            ...styles.card,
            borderColor: isActive ? 'rgba(0,229,255,0.2)' : 'var(--border)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: isActive ? 'var(--green)' : 'var(--border2)',
                  animation: isActive ? 'pulse-dot 1s infinite' : 'none',
                }} />
                <span style={{ fontSize: 11, fontWeight: 600, color: isActive ? 'var(--text)' : 'var(--text2)' }}>
                  {stage.label}
                </span>
              </div>
              <span style={{ fontSize: 9, letterSpacing: 1.5, color: isActive ? 'var(--green)' : 'var(--text3)' }}>
                {isActive ? 'RUNNING' : 'IDLE'}
              </span>
            </div>
            <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.5 }}>{stage.desc}</div>
            {isActive && agentStatus.message && (
              <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text2)', fontStyle: 'italic', lineHeight: 1.5 }}>
                {agentStatus.message}
              </div>
            )}
            {isActive && agentStatus.round && (
              <div style={{ marginTop: 4, fontSize: 9, color: 'var(--text3)', letterSpacing: 1 }}>
                ROUND {agentStatus.round} / {agentStatus.max_rounds || 1}
              </div>
            )}
          </div>
        )
      })}

      <div style={{ ...styles.card, marginTop: 4 }}>
        <div style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5, marginBottom: 8 }}>PIPELINE FLOW</div>
        <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 2 }}>
          <span style={{ color: 'var(--accent)' }}>MMSI INVESTIGATION</span><br/>
          News · Sanctions · Geo agents run in parallel<br/>
          → Reporter synthesises findings<br/>
          → Critic reviews — exits early if approved
        </div>
      </div>
    </div>
  )
}

const LOG_COLORS = {
  incident:           'var(--warning)',
  eval:               'var(--accent)',
  agent:              'var(--green)',
  critic:             'var(--warning)',
  threshold:          'var(--danger)',
  report:             'var(--green)',
  error:              'var(--danger)',
  system:             'var(--text3)',
  news_agent:         'var(--accent)',
  sanctions_agent:    'var(--warning)',
  geopolitical_agent: 'var(--danger)',
  investigation:      'var(--green)',
}

const LOG_ICONS = {
  incident:           '⚑',
  eval:               '◈',
  agent:              '▶',
  critic:             '◎',
  threshold:          '!',
  report:             '★',
  error:              '✕',
  system:             '·',
  news_agent:         '◈',
  sanctions_agent:    '⚑',
  geopolitical_agent: '◉',
  investigation:      '▶',
}

function LogTab({ logs, onOpenReport, hasReport }) {
  if (logs.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={{ color: 'var(--text3)', fontSize: 11, letterSpacing: 1 }}>AWAITING EVENTS</div>
        <div style={{ color: 'var(--text3)', fontSize: 9, letterSpacing: 0.5, marginTop: 6, opacity: 0.6 }}>
          Pipeline activity will appear here
        </div>
      </div>
    )
  }

  return (
    <div style={styles.scrollArea}>
      {hasReport && (
        <button style={{ ...styles.viewReportBtn, marginBottom: 6 }} onClick={onOpenReport}>
          VIEW INTELLIGENCE REPORT ★
        </button>
      )}
      {logs.map((entry, i) => {
        const color = LOG_COLORS[entry.kind] || 'var(--text3)'
        const icon = LOG_ICONS[entry.kind] || '·'
        return (
          <div key={i} style={{
            display: 'flex', gap: 8, alignItems: 'flex-start',
            padding: '7px 10px',
            borderBottom: '1px solid var(--border)',
            background: entry.kind === 'report' ? 'rgba(0,229,255,0.03)'
              : entry.kind === 'error' ? 'rgba(255,51,85,0.04)' : 'transparent',
          }}>
            <span style={{ fontSize: 10, color, flexShrink: 0, marginTop: 1, width: 10, textAlign: 'center' }}>{icon}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: color === 'var(--text3)' ? 'var(--text3)' : 'var(--text2)', lineHeight: 1.5, wordBreak: 'break-word' }}>
                {entry.text}
              </div>
              {entry.round && (
                <div style={{ fontSize: 9, color: 'var(--text3)', marginTop: 2 }}>round {entry.round}</div>
              )}
            </div>
            <span style={{ fontSize: 9, color: 'var(--text3)', flexShrink: 0, marginTop: 1 }}>{entry.ts}</span>
          </div>
        )
      })}
    </div>
  )
}

const styles = {
  panel: {
    width: 300, flexShrink: 0,
    display: 'flex', flexDirection: 'column',
    background: 'var(--bg)', borderLeft: '1px solid var(--border)',
  },
  tabs: {
    display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0,
  },
  tab: {
    flex: 1, padding: '12px 0', background: 'transparent', border: 'none',
    color: 'var(--text3)', fontSize: 9, letterSpacing: 2, cursor: 'pointer',
    transition: 'color 0.15s', fontFamily: 'inherit',
  },
  tabActive: {
    color: 'var(--text)', borderBottom: '1px solid var(--text)',
  },
  scrollArea: {
    flex: 1, overflowY: 'auto', padding: '12px',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  empty: {
    flex: 1, display: 'flex', flexDirection: 'column',
    alignItems: 'center', justifyContent: 'center', gap: 12,
  },
  emptyIcon: { opacity: 0.4 },
  card: {
    background: 'var(--panel)',
    border: '1px solid var(--border)',
    padding: '12px 14px',
  },
  cardHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6,
  },
  alertBanner: {
    padding: '6px 10px',
    border: '1px solid rgba(255,51,85,0.3)',
    fontSize: 9, color: 'var(--danger)', letterSpacing: 2,
    animation: 'blink 2s infinite',
  },
  viewReportBtn: {
    width: '100%', padding: '12px',
    background: 'transparent',
    border: '1px solid rgba(255,255,255,0.12)',
    color: 'var(--text2)', fontSize: 9, fontWeight: 600,
    cursor: 'pointer', letterSpacing: 2.5, fontFamily: 'inherit',
    transition: 'border-color 0.15s, color 0.15s',
  },
  reportCta: {
    padding: '14px', background: 'transparent',
    border: 'none', borderTop: '1px solid var(--border)',
    color: 'var(--text)', fontSize: 9, fontWeight: 700,
    cursor: 'pointer', letterSpacing: 3, fontFamily: 'inherit',
    flexShrink: 0, animation: 'blink 3s infinite',
  },
  abortBtn: {
    padding: '12px', background: 'transparent',
    border: 'none', borderTop: '1px solid rgba(255,51,85,0.2)',
    color: 'var(--danger)', fontSize: 9, fontWeight: 600,
    cursor: 'pointer', letterSpacing: 3, fontFamily: 'inherit',
    flexShrink: 0, transition: 'background 0.15s',
  },
}
