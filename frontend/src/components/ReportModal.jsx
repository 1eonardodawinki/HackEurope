import { useState } from 'react'

export default function ReportModal({ report, onClose }) {
  const [showReasoning, setShowReasoning] = useState(false)

  if (!report) return null

  const meta = report._meta || {}
  const predictions = report.commodity_predictions || []
  const evidence = report.supporting_evidence || []
  const risks = report.risk_factors || []

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} className="animate-slide-up" onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={styles.header}>
          <div>
            <div style={styles.classification}>{report.classification || 'INTELLIGENCE REPORT — RESTRICTED'}</div>
            <div style={styles.title}>{report.title || 'Maritime Intelligence Assessment'}</div>
            <div style={styles.meta}>
              Region: {meta.region} &nbsp;|&nbsp;
              Incidents: {meta.incident_count} &nbsp;|&nbsp;
              Critic rounds: {meta.critic_rounds} &nbsp;|&nbsp;
              <span style={{ color: meta.final_approved ? 'var(--green)' : 'var(--warning)' }}>
                {meta.final_approved ? '✓ APPROVED' : '⚠ PROVISIONAL'}
              </span>
            </div>
          </div>

          <div style={styles.headerRight}>
            <ConfidenceMeter value={report.overall_confidence} />
            <button style={styles.closeBtn} onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Body */}
        <div style={styles.body}>

          {/* Executive Summary */}
          <section style={styles.section}>
            <SectionTitle>Executive Summary</SectionTitle>
            <p style={styles.para}>{report.executive_summary}</p>
          </section>

          {/* Commodity Predictions — the star of the show */}
          {predictions.length > 0 && (
            <section style={styles.section}>
              <SectionTitle>Commodity Market Impact Forecast</SectionTitle>
              <div style={styles.predictionsGrid}>
                {predictions.map((pred, i) => (
                  <CommodityCard key={i} prediction={pred} />
                ))}
              </div>
            </section>
          )}

          {/* Threat Assessment */}
          {report.threat_assessment && (
            <section style={styles.section}>
              <SectionTitle>Threat Assessment</SectionTitle>
              <p style={styles.para}>{report.threat_assessment}</p>
            </section>
          )}

          {/* Evidence */}
          {evidence.length > 0 && (
            <section style={styles.section}>
              <SectionTitle>Supporting Evidence</SectionTitle>
              <div style={styles.evidenceList}>
                {evidence.map((e, i) => (
                  <div key={i} style={styles.evidenceItem}>
                    <span style={{ color: 'var(--accent)', marginRight: 8 }}>▸</span>{e}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Risk Factors */}
          {risks.length > 0 && (
            <section style={styles.section}>
              <SectionTitle>Risk Factors</SectionTitle>
              <div style={styles.evidenceList}>
                {risks.map((r, i) => (
                  <div key={i} style={{ ...styles.evidenceItem, borderColor: 'rgba(255,149,0,0.2)', background: 'rgba(255,149,0,0.04)' }}>
                    <span style={{ color: 'var(--warning)', marginRight: 8 }}>⚠</span>{r}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Chain of Thought (collapsible) */}
          {report.chain_of_thought && (
            <section style={styles.section}>
              <button style={styles.toggleBtn} onClick={() => setShowReasoning(v => !v)}>
                <SectionTitle style={{ margin: 0 }}>Analyst Reasoning Chain</SectionTitle>
                <span style={{ color: 'var(--text3)', fontSize: 12 }}>{showReasoning ? '▲' : '▼'}</span>
              </button>
              {showReasoning && (
                <div style={styles.reasoning} className="animate-fade-in">
                  {report.chain_of_thought}
                </div>
              )}
            </section>
          )}

          {/* Critic badge */}
          <div style={styles.criticFooter}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 12 }}>🤖</span>
              <span style={{ color: 'var(--text2)', fontSize: 11 }}>
                Critic Agent reviewed {meta.critic_rounds || 1} round{meta.critic_rounds !== 1 ? 's' : ''}
              </span>
              {meta.critic_quality_score && (
                <span style={{ color: 'var(--text3)', fontSize: 10 }}>
                  — Quality score: {meta.critic_quality_score}/100
                </span>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <span style={{ fontSize: 10, color: 'var(--text3)' }}>Powered by Claude Opus 4.6</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function CommodityCard({ prediction: p }) {
  const isPositive = (p.predicted_change_pct_high || 0) > 0
  const changeStr = p.predicted_change_pct_low != null
    ? `${isPositive ? '+' : ''}${p.predicted_change_pct_low}% to ${isPositive ? '+' : ''}${p.predicted_change_pct_high}%`
    : `${isPositive ? '+' : ''}${p.predicted_change_pct || 0}%`
  const conf = p.confidence || 0

  return (
    <div style={styles.commodityCard}>
      <div style={styles.commodityName}>{p.commodity}</div>

      <div style={styles.priceRow}>
        {p.current_price && (
          <div>
            <div style={styles.priceLabel}>Current</div>
            <div style={styles.price}>{p.current_price} <span style={{ fontSize: 10 }}>{p.currency || 'USD'}</span></div>
          </div>
        )}
        <div>
          <div style={styles.priceLabel}>Forecast</div>
          <div style={{ ...styles.price, color: isPositive ? 'var(--danger)' : 'var(--green)', fontSize: 18 }}>
            {changeStr}
          </div>
        </div>
      </div>

      <div style={styles.timeframe}>{p.timeframe}</div>

      {/* Confidence bar */}
      <div style={{ marginTop: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ fontSize: 9, color: 'var(--text3)' }}>CONFIDENCE</span>
          <span style={{ fontSize: 10, color: conf >= 70 ? 'var(--danger)' : conf >= 45 ? 'var(--warning)' : 'var(--text2)' }}>
            {conf}%
          </span>
        </div>
        <div style={styles.confBar}>
          <div style={{
            ...styles.confFill,
            width: `${conf}%`,
            background: conf >= 70 ? 'var(--danger)' : conf >= 45 ? 'var(--warning)' : 'var(--accent2)',
          }} />
        </div>
      </div>

      {p.reasoning && (
        <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text3)', lineHeight: 1.5 }}>
          {p.reasoning.slice(0, 120)}{p.reasoning.length > 120 ? '...' : ''}
        </div>
      )}
    </div>
  )
}

function ConfidenceMeter({ value }) {
  const v = value || 0
  const color = v >= 70 ? 'var(--danger)' : v >= 50 ? 'var(--warning)' : 'var(--text2)'
  const circumference = 2 * Math.PI * 28
  const offset = circumference - (v / 100) * circumference

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="28" fill="none" stroke="var(--border)" strokeWidth="4" />
        <circle cx="36" cy="36" r="28" fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 36 36)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x="36" y="40" textAnchor="middle" fill={color} fontSize="16" fontWeight="700"
          fontFamily="monospace">{v}</text>
      </svg>
      <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1 }}>CONFIDENCE</span>
    </div>
  )
}

function SectionTitle({ children, style }) {
  return (
    <div style={{ fontSize: 10, letterSpacing: 2, color: 'var(--accent)', fontWeight: 700,
      marginBottom: 10, textTransform: 'uppercase', ...style }}>
      {children}
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)',
    backdropFilter: 'blur(4px)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20,
  },
  modal: {
    width: '100%', maxWidth: 860,
    maxHeight: '90vh', display: 'flex', flexDirection: 'column',
    background: 'var(--panel)', border: '1px solid var(--border2)',
    borderRadius: 10, overflow: 'hidden',
    boxShadow: '0 0 60px rgba(0,229,255,0.1), 0 20px 60px rgba(0,0,0,0.6)',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    padding: '20px 24px', background: 'var(--panel2)',
    borderBottom: '1px solid var(--border2)', flexShrink: 0,
  },
  classification: {
    fontSize: 9, letterSpacing: 2, color: 'var(--danger)', marginBottom: 6, fontWeight: 700,
  },
  title: {
    fontSize: 20, fontWeight: 700, color: 'var(--text)', marginBottom: 6, lineHeight: 1.2,
  },
  meta: {
    fontSize: 10, color: 'var(--text3)',
  },
  headerRight: {
    display: 'flex', alignItems: 'flex-start', gap: 16,
  },
  closeBtn: {
    background: 'transparent', border: '1px solid var(--border2)', color: 'var(--text2)',
    width: 28, height: 28, borderRadius: 4, cursor: 'pointer', fontSize: 14,
    fontFamily: 'inherit',
  },
  body: {
    flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 0,
  },
  section: {
    marginBottom: 24,
  },
  para: {
    fontSize: 13, color: 'var(--text2)', lineHeight: 1.7,
  },
  predictionsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12,
  },
  commodityCard: {
    background: 'var(--panel2)', border: '1px solid var(--border2)',
    borderRadius: 8, padding: '14px 16px',
  },
  commodityName: {
    fontSize: 12, fontWeight: 700, color: 'var(--text)', marginBottom: 10,
  },
  priceRow: {
    display: 'flex', gap: 20, marginBottom: 6,
  },
  priceLabel: {
    fontSize: 9, color: 'var(--text3)', marginBottom: 2, letterSpacing: 1,
  },
  price: {
    fontSize: 15, fontWeight: 700, color: 'var(--text)',
  },
  timeframe: {
    fontSize: 10, color: 'var(--text3)', fontStyle: 'italic',
  },
  confBar: {
    height: 3, background: 'var(--border)', borderRadius: 2, overflow: 'hidden',
  },
  confFill: {
    height: '100%', borderRadius: 2, transition: 'width 1s ease',
  },
  evidenceList: {
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  evidenceItem: {
    padding: '7px 10px', background: 'rgba(0,229,255,0.04)',
    border: '1px solid rgba(0,229,255,0.15)', borderRadius: 4,
    fontSize: 12, color: 'var(--text2)', lineHeight: 1.5,
  },
  toggleBtn: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0,
    marginBottom: 8,
  },
  reasoning: {
    fontSize: 12, color: 'var(--text3)', lineHeight: 1.8,
    background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border)',
    borderRadius: 6, padding: 14, fontStyle: 'italic',
    whiteSpace: 'pre-wrap',
  },
  criticFooter: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '12px 0', borderTop: '1px solid var(--border)',
    marginTop: 8,
  },
}
