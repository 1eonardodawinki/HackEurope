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
          <div style={{ flex: 1 }}>
            <div style={styles.classification}>{report.classification || 'INTELLIGENCE REPORT — RESTRICTED'}</div>
            <div style={styles.title}>{report.title || 'Maritime Intelligence Assessment'}</div>
            <div style={styles.meta}>
              {meta.region} &nbsp;·&nbsp; {meta.incident_count} incidents &nbsp;·&nbsp;
              {meta.critic_rounds} critic round{meta.critic_rounds !== 1 ? 's' : ''} &nbsp;·&nbsp;
              <span style={{ color: meta.final_approved ? 'var(--green)' : 'var(--warning)' }}>
                {meta.final_approved ? 'APPROVED' : 'PROVISIONAL'}
              </span>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 20 }}>
            <ConfidenceMeter value={report.overall_confidence} />
            <button style={styles.closeBtn} onClick={onClose}>✕</button>
          </div>
        </div>

        {/* Body */}
        <div style={styles.body}>

          <section style={styles.section}>
            <Label>Executive Summary</Label>
            <p style={styles.para}>{report.executive_summary}</p>
          </section>

          {predictions.length > 0 && (
            <section style={styles.section}>
              <Label>Commodity Market Impact Forecast</Label>
              <div style={styles.predictionsGrid}>
                {predictions.map((pred, i) => (
                  <CommodityCard key={i} prediction={pred} />
                ))}
              </div>
            </section>
          )}

          {report.threat_assessment && (
            <section style={styles.section}>
              <Label>Threat Assessment</Label>
              <p style={styles.para}>{report.threat_assessment}</p>
            </section>
          )}

          {evidence.length > 0 && (
            <section style={styles.section}>
              <Label>Supporting Evidence</Label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {evidence.map((e, i) => (
                  <div key={i} style={styles.evidenceItem}>
                    <span style={{ color: 'var(--accent)', marginRight: 10, flexShrink: 0 }}>—</span>{e}
                  </div>
                ))}
              </div>
            </section>
          )}

          {risks.length > 0 && (
            <section style={styles.section}>
              <Label>Risk Factors</Label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {risks.map((r, i) => (
                  <div key={i} style={{ ...styles.evidenceItem, borderColor: 'rgba(255,149,0,0.15)' }}>
                    <span style={{ color: 'var(--warning)', marginRight: 10, flexShrink: 0 }}>—</span>{r}
                  </div>
                ))}
              </div>
            </section>
          )}

          {report.chain_of_thought && (
            <section style={styles.section}>
              <button style={styles.toggleBtn} onClick={() => setShowReasoning(v => !v)}>
                <Label style={{ margin: 0 }}>Analyst Reasoning Chain</Label>
                <span style={{ color: 'var(--text3)', fontSize: 10 }}>{showReasoning ? '▲' : '▼'}</span>
              </button>
              {showReasoning && (
                <div style={styles.reasoning} className="animate-fade-in">
                  {report.chain_of_thought}
                </div>
              )}
            </section>
          )}

          <div style={styles.footer}>
            <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1 }}>
              CRITIC AGENT — {meta.critic_rounds || 1} REVIEW ROUND{meta.critic_rounds !== 1 ? 'S' : ''}
              {meta.critic_quality_score ? ` — QUALITY ${meta.critic_quality_score}/100` : ''}
            </span>
            <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1 }}>CLAUDE OPUS 4.6</span>
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
      <div style={{ fontSize: 9, fontWeight: 600, color: 'var(--text3)', letterSpacing: 2, marginBottom: 10 }}>
        {p.commodity}
      </div>

      <div style={{ display: 'flex', gap: 20, marginBottom: 8 }}>
        {p.current_price && (
          <div>
            <div style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1, marginBottom: 3 }}>CURRENT</div>
            <div style={{ fontSize: 14, fontWeight: 300, color: 'var(--text)' }}>
              {p.current_price} <span style={{ fontSize: 9 }}>{p.currency || 'USD'}</span>
            </div>
          </div>
        )}
        <div>
          <div style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1, marginBottom: 3 }}>FORECAST</div>
          <div style={{ fontSize: 18, fontWeight: 300, color: isPositive ? 'var(--danger)' : 'var(--green)' }}>
            {changeStr}
          </div>
        </div>
      </div>

      <div style={{ fontSize: 9, color: 'var(--text3)', marginBottom: 10 }}>{p.timeframe}</div>

      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 1.5 }}>CONFIDENCE</span>
        <span style={{ fontSize: 9, color: conf >= 70 ? 'var(--danger)' : conf >= 45 ? 'var(--warning)' : 'var(--text3)' }}>
          {conf}%
        </span>
      </div>
      <div style={{ height: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
        <div style={{
          height: '100%', width: `${conf}%`, transition: 'width 1s ease',
          background: conf >= 70 ? 'var(--danger)' : conf >= 45 ? 'var(--warning)' : 'var(--text3)',
        }} />
      </div>

      {p.reasoning && (
        <div style={{ marginTop: 10, fontSize: 10, color: 'var(--text3)', lineHeight: 1.6 }}>
          {p.reasoning.slice(0, 120)}{p.reasoning.length > 120 ? '…' : ''}
        </div>
      )}
    </div>
  )
}

function ConfidenceMeter({ value }) {
  const v = value || 0
  const color = v >= 70 ? 'var(--danger)' : v >= 50 ? 'var(--warning)' : 'var(--text3)'
  const circumference = 2 * Math.PI * 26
  const offset = circumference - (v / 100) * circumference

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle cx="34" cy="34" r="26" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" />
        <circle cx="34" cy="34" r="26" fill="none" stroke={color} strokeWidth="1.5"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 34 34)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x="34" y="39" textAnchor="middle" fill={color} fontSize="15" fontWeight="300"
          fontFamily="-apple-system,BlinkMacSystemFont,'Inter',sans-serif">{v}</text>
      </svg>
      <span style={{ fontSize: 8, color: 'var(--text3)', letterSpacing: 2 }}>CONFIDENCE</span>
    </div>
  )
}

function Label({ children, style }) {
  return (
    <div style={{ fontSize: 9, letterSpacing: 2.5, color: 'var(--text3)', fontWeight: 600,
      marginBottom: 12, textTransform: 'uppercase', ...style }}>
      {children}
    </div>
  )
}

const styles = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)',
    backdropFilter: 'blur(6px)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  modal: {
    width: '100%', maxWidth: 860,
    maxHeight: '90vh', display: 'flex', flexDirection: 'column',
    background: '#080808', border: '1px solid rgba(255,255,255,0.1)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    padding: '20px 24px',
    borderBottom: '1px solid rgba(255,255,255,0.08)', flexShrink: 0,
  },
  classification: {
    fontSize: 9, letterSpacing: 3, color: 'var(--danger)', marginBottom: 8, fontWeight: 600,
  },
  title: {
    fontSize: 18, fontWeight: 300, color: 'var(--text)', marginBottom: 8, lineHeight: 1.3,
    letterSpacing: -0.3,
  },
  meta: {
    fontSize: 10, color: 'var(--text3)', letterSpacing: 0.5,
  },
  closeBtn: {
    background: 'transparent', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--text3)',
    width: 28, height: 28, cursor: 'pointer', fontSize: 12,
    fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  body: {
    flex: 1, overflowY: 'auto', padding: '20px 24px',
    display: 'flex', flexDirection: 'column', gap: 0,
  },
  section: { marginBottom: 28 },
  para: {
    fontSize: 13, color: 'var(--text2)', lineHeight: 1.8, fontWeight: 300,
  },
  predictionsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8,
  },
  commodityCard: {
    background: '#0f0f0f', border: '1px solid rgba(255,255,255,0.08)',
    padding: '14px 16px',
  },
  evidenceItem: {
    display: 'flex', padding: '8px 10px',
    border: '1px solid rgba(0,229,255,0.1)',
    fontSize: 12, color: 'var(--text2)', lineHeight: 1.6,
  },
  toggleBtn: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: 0,
    marginBottom: 10,
  },
  reasoning: {
    fontSize: 11, color: 'var(--text3)', lineHeight: 1.9,
    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
    padding: 14, fontStyle: 'italic', whiteSpace: 'pre-wrap',
  },
  footer: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '14px 0', borderTop: '1px solid rgba(255,255,255,0.06)',
    marginTop: 8,
  },
}
