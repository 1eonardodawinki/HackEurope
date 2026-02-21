import { useState } from 'react'

const TYPE_LABELS = {
  ais_dropout: 'AIS DROPOUT',
  ship_proximity: 'PROXIMITY',
}

const SEVERITY_COLORS = {
  high: 'var(--danger)',
  medium: 'var(--warning)',
  low: 'var(--text3)',
}

const TAB_LABELS = { incidents: 'INC', regions: 'ZONES', agents: 'AGENTS', log: 'LOG' }

export default function IncidentPanel({
  incidents, thresholds, agentStatus, hotzones, logs, onOpenReport, hasReport
}) {
  const [activeTab, setActiveTab] = useState('incidents')

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

      {activeTab === 'incidents' && <IncidentsTab incidents={incidents} />}
      {activeTab === 'regions' && (
        <RegionsTab hotzones={hotzones} thresholds={thresholds} onOpenReport={onOpenReport} hasReport={hasReport} />
      )}
      {activeTab === 'agents' && <AgentsTab agentStatus={agentStatus} />}
      {activeTab === 'log' && <LogTab logs={logs || []} onOpenReport={onOpenReport} hasReport={hasReport} />}

      {hasReport && (
        <button style={styles.reportCta} onClick={onOpenReport}>
          VIEW INTELLIGENCE REPORT
        </button>
      )}
    </div>
  )
}

function IncidentsTab({ incidents }) {
  if (incidents.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={styles.emptyIcon}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="13" stroke="rgba(255,255,255,0.1)" strokeWidth="1"/>
            <circle cx="14" cy="14" r="8" stroke="rgba(255,255,255,0.06)" strokeWidth="1"/>
            <circle cx="14" cy="14" r="2" fill="rgba(255,255,255,0.15)"/>
          </svg>
        </div>
        <div style={{ color: 'var(--text3)', fontSize: 11, letterSpacing: 1 }}>MONITORING</div>
      </div>
    )
  }

  return (
    <div style={styles.scrollArea}>
      {incidents.map((inc, i) => (
        <div key={inc.id} className="animate-sweep-in"
          style={{ ...styles.card, animationDelay: `${i * 20}ms` }}>

          <div style={styles.cardHeader}>
            <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: 2,
              color: SEVERITY_COLORS[inc.severity] || 'var(--warning)' }}>
              {TYPE_LABELS[inc.type] || inc.type}
            </span>
            <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 0.5 }}>
              {new Date(inc.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>

          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 8, lineHeight: 1.3 }}>
            {inc.ship_name || `MMSI ${inc.mmsi}`}
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 8 }}>
            <MetaItem label="Region" value={inc.region} />
            {inc.duration_minutes > 0 && <MetaItem label="Duration" value={`${inc.duration_minutes}m`} />}
            {inc.confidence_score && (
              <MetaItem label="Confidence" value={`${inc.confidence_score}%`} color="var(--accent)" />
            )}
          </div>

          {inc.commodities_affected?.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 8 }}>
              {inc.commodities_affected.map(c => (
                <span key={c} style={styles.tag}>{c}</span>
              ))}
            </div>
          )}

          {inc.confidence_score && (
            <div style={styles.bar}>
              <div style={{
                ...styles.barFill,
                width: `${inc.confidence_score}%`,
                background: inc.confidence_score >= 70 ? 'var(--danger)' :
                  inc.confidence_score >= 45 ? 'var(--warning)' : 'var(--text3)',
              }} />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function RegionsTab({ hotzones, thresholds, onOpenReport, hasReport }) {
  return (
    <div style={styles.scrollArea}>
      {Object.entries(hotzones).map(([name, hz]) => {
        const t = thresholds[name]
        const count = t?.incident_count || 0
        const threshold = t?.threshold || 3
        const pct = Math.min((count / threshold) * 100, 100)
        const conf = t?.avg_confidence || 0
        const exceeded = count >= threshold

        return (
          <div key={name} style={styles.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 8, height: 8, background: hz.color, flexShrink: 0 }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', letterSpacing: 0.3 }}>{name}</span>
              </div>
              <span style={{ fontSize: 10, color: exceeded ? 'var(--danger)' : 'var(--text3)' }}>
                {count}/{threshold}
              </span>
            </div>

            <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 12, lineHeight: 1.6 }}>
              {hz.description}
            </div>

            <div style={{ marginBottom: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5 }}>THREAT THRESHOLD</span>
                <span style={{ fontSize: 9, color: exceeded ? 'var(--danger)' : 'var(--text3)' }}>
                  {exceeded ? 'EXCEEDED' : `${threshold - count} remaining`}
                </span>
              </div>
              <div style={styles.bar}>
                <div style={{
                  ...styles.barFill,
                  width: `${pct}%`,
                  background: pct >= 100 ? 'var(--danger)' : pct >= 60 ? 'var(--warning)' : 'var(--text3)',
                }} />
              </div>
            </div>

            {conf > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5 }}>AVG CONFIDENCE</span>
                <span style={{ fontSize: 10, color: conf >= 70 ? 'var(--danger)' : 'var(--warning)' }}>
                  {conf.toFixed(0)}%
                </span>
              </div>
            )}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {hz.commodities.map(c => (
                <span key={c} style={styles.tag}>{c}</span>
              ))}
            </div>

            {exceeded && (
              <div style={styles.alertBanner}>
                INTELLIGENCE THRESHOLD EXCEEDED
              </div>
            )}
          </div>
        )
      })}

      {hasReport && (
        <button style={styles.viewReportBtn} onClick={onOpenReport}>
          VIEW FULL INTELLIGENCE REPORT
        </button>
      )}
    </div>
  )
}

function AgentsTab({ agentStatus }) {
  const stages = [
    { id: 'evaluator', label: 'Evaluator', desc: 'Assesses incidents using news & commodity data' },
    { id: 'reporter', label: 'Reporter', desc: 'Generates structured intelligence report' },
    { id: 'critic', label: 'Critic', desc: 'Adversarial review — forces high-quality output' },
  ]

  return (
    <div style={styles.scrollArea}>
      <div style={{ fontSize: 10, color: 'var(--text3)', letterSpacing: 0.5, marginBottom: 16, lineHeight: 1.6 }}>
        Multi-agent pipeline — Claude Opus 4.6
      </div>

      {stages.map(stage => {
        const isActive = agentStatus.stage === stage.id
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
                ROUND {agentStatus.round} / {agentStatus.max_rounds || 3}
              </div>
            )}
          </div>
        )
      })}

      <div style={{ ...styles.card, marginTop: 4 }}>
        <div style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5, marginBottom: 8 }}>PIPELINE FLOW</div>
        <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 2 }}>
          1. Evaluator scores each incident (0–100%)<br/>
          2. When 3+ incidents detected — Reporter generates report<br/>
          3. Critic reviews adversarially (up to 3 rounds)<br/>
          4. Approved report delivered to analysts
        </div>
      </div>
    </div>
  )
}

const LOG_COLORS = {
  incident:  'var(--warning)',
  eval:      'var(--accent)',
  agent:     'var(--green)',
  critic:    'var(--warning)',
  threshold: 'var(--danger)',
  report:    'var(--green)',
  error:     'var(--danger)',
  system:    'var(--text3)',
}

const LOG_ICONS = {
  incident:  '⚑',
  eval:      '◈',
  agent:     '▶',
  critic:    '◎',
  threshold: '!',
  report:    '★',
  error:     '✕',
  system:    '·',
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

function MetaItem({ label, value, color }) {
  return (
    <span style={{ fontSize: 10, color: 'var(--text3)' }}>
      {label}: <span style={{ color: color || 'var(--text2)' }}>{value}</span>
    </span>
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
  tag: {
    fontSize: 9, padding: '2px 7px',
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.08)',
    color: 'var(--text3)', letterSpacing: 0.5,
  },
  bar: {
    height: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden',
  },
  barFill: {
    height: '100%', transition: 'width 0.6s ease',
  },
  alertBanner: {
    marginTop: 10, padding: '6px 10px',
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
}
