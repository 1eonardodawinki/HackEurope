import { useState } from 'react'

const TYPE_LABELS = {
  ais_dropout: 'AIS DROPOUT',
  ship_proximity: 'PROXIMITY',
}

const SEVERITY_COLORS = {
  high: 'var(--danger)',
  medium: 'var(--warning)',
  low: '#7a99bb',
}

export default function IncidentPanel({
  incidents, thresholds, agentStatus, hotzones, onOpenReport, hasReport
}) {
  const [activeTab, setActiveTab] = useState('incidents')

  return (
    <div style={styles.panel}>
      {/* Tabs */}
      <div style={styles.tabs}>
        {['incidents', 'regions', 'agents'].map(tab => (
          <button key={tab} style={{ ...styles.tab, ...(activeTab === tab ? styles.tabActive : {}) }}
            onClick={() => setActiveTab(tab)}>
            {tab.toUpperCase()}
          </button>
        ))}
      </div>

      {activeTab === 'incidents' && (
        <IncidentsTab incidents={incidents} />
      )}
      {activeTab === 'regions' && (
        <RegionsTab hotzones={hotzones} thresholds={thresholds} onOpenReport={onOpenReport} hasReport={hasReport} />
      )}
      {activeTab === 'agents' && (
        <AgentsTab agentStatus={agentStatus} />
      )}

      {/* Report CTA if available */}
      {hasReport && (
        <button style={styles.reportCta} onClick={onOpenReport}>
          <span style={{ fontSize: 14 }}>📊</span>
          <span>VIEW INTELLIGENCE REPORT</span>
        </button>
      )}
    </div>
  )
}

function IncidentsTab({ incidents }) {
  if (incidents.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>🛰️</div>
        <div style={{ color: 'var(--text2)', fontSize: 12 }}>Monitoring for incidents...</div>
      </div>
    )
  }

  return (
    <div style={styles.scrollArea}>
      {incidents.map((inc, i) => (
        <div key={inc.id} className="animate-sweep-in" style={{ ...styles.incidentCard, animationDelay: `${i * 30}ms` }}>
          <div style={styles.incidentHeader}>
            <span style={{ ...styles.incidentType, color: SEVERITY_COLORS[inc.severity] || 'var(--warning)' }}>
              ▲ {TYPE_LABELS[inc.type] || inc.type}
            </span>
            <span style={styles.incidentTime}>
              {new Date(inc.timestamp).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </span>
          </div>

          <div style={styles.incidentShip}>{inc.ship_name || `MMSI ${inc.mmsi}`}</div>

          <div style={styles.incidentMeta}>
            <MetaItem label="Region" value={inc.region} />
            {inc.duration_minutes > 0 && <MetaItem label="Duration" value={`${inc.duration_minutes}m`} />}
            {inc.confidence_score && (
              <MetaItem label="Confidence" value={`${inc.confidence_score}%`} color="var(--accent)" />
            )}
          </div>

          {inc.commodities_affected?.length > 0 && (
            <div style={styles.commodityTags}>
              {inc.commodities_affected.map(c => (
                <span key={c} style={styles.commodityTag}>{c}</span>
              ))}
            </div>
          )}

          {inc.confidence_score && (
            <div style={styles.confBar}>
              <div style={{
                ...styles.confFill,
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

        return (
          <div key={name} style={styles.regionCard}>
            <div style={styles.regionHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ width: 10, height: 10, borderRadius: 2, background: hz.color }} />
                <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text)' }}>{name}</span>
              </div>
              <span style={{ fontSize: 11, color: count >= threshold ? 'var(--danger)' : 'var(--text2)' }}>
                {count}/{threshold} incidents
              </span>
            </div>

            <div style={styles.regionDesc}>{hz.description}</div>

            {/* Threshold bar */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                <span style={{ fontSize: 9, color: 'var(--text3)' }}>THREAT THRESHOLD</span>
                <span style={{ fontSize: 9, color: count >= threshold ? 'var(--danger)' : 'var(--text2)' }}>
                  {count >= threshold ? '⚠ EXCEEDED' : `${threshold - count} remaining`}
                </span>
              </div>
              <div style={styles.thresholdBar}>
                <div style={{
                  ...styles.thresholdFill,
                  width: `${pct}%`,
                  background: pct >= 100 ? 'var(--danger)' : pct >= 60 ? 'var(--warning)' : 'var(--accent2)',
                  boxShadow: pct >= 100 ? 'var(--glow-danger)' : pct >= 60 ? 'var(--glow-warning)' : 'none',
                }} />
              </div>
            </div>

            {conf > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span style={{ fontSize: 9, color: 'var(--text3)' }}>AVG CONFIDENCE</span>
                <span style={{ fontSize: 11, color: conf >= 70 ? 'var(--danger)' : 'var(--warning)' }}>
                  {conf.toFixed(0)}%
                </span>
              </div>
            )}

            <div style={styles.commodityList}>
              {hz.commodities.map(c => (
                <span key={c} style={styles.commodityTag}>{c}</span>
              ))}
            </div>

            {count >= threshold && (
              <div style={styles.alertBanner}>
                ⚠ INTELLIGENCE THRESHOLD EXCEEDED — REPORT GENERATING
              </div>
            )}
          </div>
        )
      })}

      {hasReport && (
        <button style={styles.viewReportBtn} onClick={onOpenReport}>
          📊 VIEW FULL INTELLIGENCE REPORT
        </button>
      )}
    </div>
  )
}

function AgentsTab({ agentStatus }) {
  const stages = [
    { id: 'evaluator', label: 'Evaluator Agent', desc: 'Assesses individual incidents using news & commodity data' },
    { id: 'reporter', label: 'Reporter Agent', desc: 'Generates structured intelligence report' },
    { id: 'critic', label: 'Critic Agent', desc: 'Adversarial review — forces high-quality reports' },
  ]

  return (
    <div style={styles.scrollArea}>
      <div style={{ padding: '8px 0', marginBottom: 8, color: 'var(--text2)', fontSize: 11 }}>
        Multi-agent pipeline powered by Claude Opus 4.6
      </div>

      {stages.map(stage => {
        const isActive = agentStatus.stage === stage.id
        const isApproval = agentStatus.stage === 'critic_result' && stage.id === 'critic'
        return (
          <div key={stage.id} style={{
            ...styles.agentCard,
            borderColor: isActive || isApproval ? 'var(--accent)' : 'var(--border)',
            background: isActive ? 'rgba(0,229,255,0.05)' : 'var(--panel2)',
          }}>
            <div style={styles.agentHeader}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 8, height: 8, borderRadius: '50%',
                  background: isActive ? 'var(--green)' : 'var(--border2)',
                  boxShadow: isActive ? 'var(--glow-green)' : 'none',
                  animation: isActive ? 'pulse-dot 1s infinite' : 'none',
                }} />
                <span style={{ fontSize: 12, fontWeight: 700, color: isActive ? 'var(--accent)' : 'var(--text)' }}>
                  {stage.label}
                </span>
              </div>
              <span style={{ fontSize: 10, color: isActive ? 'var(--green)' : 'var(--text3)' }}>
                {isActive ? 'RUNNING' : 'IDLE'}
              </span>
            </div>
            <div style={{ fontSize: 10, color: 'var(--text3)', lineHeight: 1.5 }}>{stage.desc}</div>

            {isActive && agentStatus.message && (
              <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text2)', fontStyle: 'italic' }}>
                {agentStatus.message}
              </div>
            )}
            {isActive && agentStatus.round && (
              <div style={{ marginTop: 4, fontSize: 10, color: 'var(--text3)' }}>
                Round {agentStatus.round} / {agentStatus.max_rounds || 3}
              </div>
            )}
          </div>
        )
      })}

      <div style={styles.agentNote}>
        <div style={{ marginBottom: 4, color: 'var(--text2)', fontSize: 11 }}>Pipeline Flow</div>
        <div style={{ color: 'var(--text3)', fontSize: 10, lineHeight: 1.8 }}>
          1. Evaluator scores each incident (0–100%)<br/>
          2. When ≥3 incidents detected → Reporter generates report<br/>
          3. Critic reviews adversarially (up to 3 rounds)<br/>
          4. Approved report delivered to analysts
        </div>
      </div>
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
    width: 320, flexShrink: 0,
    display: 'flex', flexDirection: 'column',
    background: 'var(--panel)', borderLeft: '1px solid var(--border)',
  },
  tabs: {
    display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0,
  },
  tab: {
    flex: 1, padding: '10px 0', background: 'transparent', border: 'none',
    color: 'var(--text3)', fontSize: 10, letterSpacing: 1.5, cursor: 'pointer',
    transition: 'color 0.15s',
  },
  tabActive: {
    color: 'var(--accent)', borderBottom: '2px solid var(--accent)',
  },
  scrollArea: {
    flex: 1, overflowY: 'auto', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 8,
  },
  empty: {
    flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', color: 'var(--text3)',
  },
  incidentCard: {
    background: 'var(--panel2)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '10px 12px',
  },
  incidentHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4,
  },
  incidentType: {
    fontSize: 10, fontWeight: 700, letterSpacing: 1,
  },
  incidentTime: {
    fontSize: 9, color: 'var(--text3)',
  },
  incidentShip: {
    fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 6,
  },
  incidentMeta: {
    display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 6,
  },
  commodityTags: {
    display: 'flex', flexWrap: 'wrap', gap: 4, marginBottom: 6,
  },
  commodityTag: {
    fontSize: 9, padding: '2px 6px', background: 'rgba(0,144,255,0.12)',
    border: '1px solid rgba(0,144,255,0.3)', borderRadius: 3, color: 'var(--accent2)',
  },
  confBar: {
    height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden',
  },
  confFill: {
    height: '100%', borderRadius: 2, transition: 'width 0.5s ease',
  },
  regionCard: {
    background: 'var(--panel2)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '12px',
  },
  regionHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6,
  },
  regionDesc: {
    fontSize: 10, color: 'var(--text3)', marginBottom: 10, lineHeight: 1.5,
  },
  thresholdBar: {
    height: 4, background: 'var(--border)', borderRadius: 2, overflow: 'hidden',
  },
  thresholdFill: {
    height: '100%', borderRadius: 2, transition: 'width 0.8s ease',
  },
  commodityList: {
    display: 'flex', flexWrap: 'wrap', gap: 4,
  },
  alertBanner: {
    marginTop: 8, padding: '6px 8px',
    background: 'rgba(255,51,85,0.12)', border: '1px solid rgba(255,51,85,0.4)',
    borderRadius: 4, fontSize: 10, color: 'var(--danger)', textAlign: 'center',
    letterSpacing: 0.5, animation: 'blink 2s infinite',
  },
  viewReportBtn: {
    width: '100%', padding: '12px', background: 'rgba(0,229,255,0.1)',
    border: '1px solid var(--accent)', borderRadius: 6, color: 'var(--accent)',
    fontSize: 11, fontWeight: 700, cursor: 'pointer', letterSpacing: 1,
    fontFamily: 'inherit',
  },
  agentCard: {
    border: '1px solid', borderRadius: 6, padding: '10px 12px',
    transition: 'border-color 0.3s, background 0.3s',
  },
  agentHeader: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4,
  },
  agentNote: {
    marginTop: 4, padding: '10px 12px',
    background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)',
    borderRadius: 6,
  },
  reportCta: {
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
    padding: '14px', background: 'linear-gradient(135deg, rgba(0,229,255,0.15), rgba(0,144,255,0.1))',
    border: '1px solid var(--accent)', borderRadius: 0,
    color: 'var(--accent)', fontSize: 12, fontWeight: 700, cursor: 'pointer',
    letterSpacing: 1.5, fontFamily: 'inherit', flexShrink: 0,
    boxShadow: 'inset 0 1px 0 rgba(0,229,255,0.1)',
    animation: 'blink 3s infinite',
  },
}
