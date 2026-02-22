import { useState } from 'react'

const API = import.meta.env.PROD ? '' : 'http://localhost:8000'

export default function ReportModal({ report, onClose }) {
  const [showReasoning, setShowReasoning] = useState(false)
  const [downloading, setDownloading] = useState(false)

  if (!report) return null

  const downloadPdf = async () => {
    if (downloading) return
    setDownloading(true)
    try {
      const resp = await fetch(`${API}/report/pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report),
      })
      const contentType = resp.headers.get('content-type') || ''
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = contentType.includes('pdf') ? 'intelligence-report.pdf' : 'intelligence-report.tex'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('PDF download failed', e)
    } finally {
      setDownloading(false)
    }
  }

  const meta         = report._meta || {}
  const isInv        = !!report.ml_risk_score
  const ml           = report.ml_risk_score
  const predictions  = report.commodity_predictions || []
  const evidence     = report.supporting_evidence   || []
  const risks        = report.risk_factors          || []
  const actions      = report.recommended_actions   || []

  const mlPct   = ml ? Math.round((ml.probability || 0) * 100) : null
  const confPct = report.overall_confidence || null

  return (
    <div style={styles.overlay} onClick={onClose}>
      <div style={styles.modal} onClick={e => e.stopPropagation()}>

        {/* ── Header ── */}
        <div style={styles.header}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={styles.classification}>
              {report.classification || 'INTELLIGENCE REPORT — RESTRICTED'}
            </div>
            <div style={styles.title}>{report.title || 'Maritime Intelligence Assessment'}</div>
            <div style={styles.metaLine}>
              {isInv ? (
                <>
                  MMSI&nbsp;{meta.mmsi || '—'}
                  &nbsp;·&nbsp;
                  <span style={{ color: riskColor(ml?.risk_tier) }}>{ml?.risk_tier || '—'}&nbsp;RISK</span>
                  &nbsp;·&nbsp;
                  <span style={{ color: meta.final_approved ? 'var(--green)' : 'var(--warning)' }}>
                    {meta.final_approved ? 'APPROVED' : 'PROVISIONAL'}
                  </span>
                </>
              ) : (
                <>
                  {meta.region}&nbsp;·&nbsp;{meta.incident_count}&nbsp;incidents&nbsp;·&nbsp;
                  <span style={{ color: meta.final_approved ? 'var(--green)' : 'var(--warning)' }}>
                    {meta.final_approved ? 'APPROVED' : 'PROVISIONAL'}
                  </span>
                </>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, flexShrink: 0 }}>
            {isInv && ml && (
              <RingMeter value={mlPct} color={riskColor(ml.risk_tier)} sublabel="ML RISK" />
            )}
            {confPct != null && (
              <RingMeter value={confPct} color={confColor(confPct)} sublabel="CONFIDENCE" />
            )}
            <button style={styles.closeBtn} onClick={onClose}>✕</button>
          </div>
        </div>

        {/* ── Body ── */}
        <div style={styles.body}>

          {/* Assessment — exec summary + threat (merged) */}
          <div style={styles.assessSection}>
            <SectionLabel>Assessment</SectionLabel>
            <p style={styles.summaryText}>{report.executive_summary}</p>
            {report.threat_assessment && report.threat_assessment !== report.executive_summary && (
              <p style={styles.threatText}>{report.threat_assessment}</p>
            )}
          </div>

          {/* ML score interpretation — inline note, no box */}
          {isInv && ml?.interpretation && (
            <p style={styles.mlInterpNote}>
              <span style={{ color: riskColor(ml.risk_tier) }}>ML {mlPct}% {ml.risk_tier}</span>
              {' — '}{ml.interpretation}
            </p>
          )}

          {/* Intel sources triptych (investigation only) */}
          {isInv && (report.news_intelligence || report.sanctions_assessment || report.geopolitical_context) && (
            <div style={{ marginBottom: 24 }}>
              <SectionLabel>Intelligence Sources</SectionLabel>
              <div style={styles.intelGrid}>
                {report.news_intelligence && (
                  <IntelCard label="NEWS" color="var(--accent)" text={report.news_intelligence} />
                )}
                {report.sanctions_assessment && (
                  <IntelCard label="SANCTIONS" color="var(--warning)" text={report.sanctions_assessment} />
                )}
                {report.geopolitical_context && (
                  <IntelCard label="GEOPOLITICAL" color="var(--danger)" text={report.geopolitical_context} />
                )}
              </div>
            </div>
          )}

          {/* Commodity predictions (standard reports only) */}
          {predictions.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <SectionLabel>Commodity Market Impact</SectionLabel>
              <div style={styles.predictionsGrid}>
                {predictions.map((p, i) => <CommodityCard key={i} prediction={p} />)}
              </div>
            </div>
          )}

          {/* Evidence + Risk factors — 2-column grid */}
          {(evidence.length > 0 || risks.length > 0) && (
            <div style={styles.evidenceGrid}>
              {evidence.length > 0 && (
                <div>
                  <SectionLabel>Supporting Evidence</SectionLabel>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {evidence.map((e, i) => (
                      <EvidenceRow key={i} text={e} accent="var(--accent)" />
                    ))}
                  </div>
                </div>
              )}
              {risks.length > 0 && (
                <div>
                  <SectionLabel>Risk Factors</SectionLabel>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {risks.map((r, i) => (
                      <EvidenceRow key={i} text={r} accent="var(--warning)" />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recommended actions */}
          {actions.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <SectionLabel>Recommended Actions</SectionLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {actions.map((a, i) => (
                  <div key={i} style={styles.actionCard}>
                    <span style={styles.actionNum}>{i + 1}</span>
                    <span style={styles.actionText}>{a}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Analyst reasoning — collapsible */}
          {report.chain_of_thought && (
            <div style={{ marginBottom: 8 }}>
              <button style={styles.toggleBtn} onClick={() => setShowReasoning(v => !v)}>
                <SectionLabel style={{ margin: 0 }}>Analyst Reasoning</SectionLabel>
                <span style={{ fontSize: 10, color: 'var(--text3)' }}>{showReasoning ? '▲' : '▼'}</span>
              </button>
              {showReasoning && (
                <div style={styles.reasoning}>{report.chain_of_thought}</div>
              )}
            </div>
          )}

          {/* Footer */}
          <div style={styles.footer}>
            <span style={styles.footerText}>
              CRITIC · {meta.critic_rounds || 1} ROUND{meta.critic_rounds !== 1 ? 'S' : ''}
              {meta.critic_quality_score ? ` · QUALITY ${meta.critic_quality_score}/100` : ''}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <button onClick={downloadPdf} disabled={downloading} style={styles.downloadBtn}>
                {downloading ? 'GENERATING…' : '↓ DOWNLOAD PDF'}
              </button>
              <span style={styles.footerText}>CLAUDE HAIKU 4.5 · PELAGOS</span>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function riskColor(tier) {
  if (tier === 'HIGH')   return 'var(--danger)'
  if (tier === 'MEDIUM') return 'var(--warning)'
  return 'var(--text3)'
}

function confColor(v) {
  if (v >= 70) return 'var(--danger)'
  if (v >= 50) return 'var(--warning)'
  return 'var(--text3)'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RingMeter({ value, sublabel, color }) {
  const v = value || 0
  const circumference = 2 * Math.PI * 26
  const offset = circumference - (v / 100) * circumference
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width="64" height="64" viewBox="0 0 68 68">
        <circle cx="34" cy="34" r="26" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1.5" />
        <circle cx="34" cy="34" r="26" fill="none" stroke={color} strokeWidth="1.5"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 34 34)"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
        <text x="34" y="38" textAnchor="middle" fill={color} fontSize="13" fontWeight="300"
          fontFamily="-apple-system,BlinkMacSystemFont,'Inter',sans-serif">{v}%</text>
      </svg>
      <span style={{ fontSize: 8, color: 'var(--text3)', letterSpacing: 2 }}>{sublabel}</span>
    </div>
  )
}

function IntelCard({ label, color, text }) {
  const [expanded, setExpanded] = useState(false)
  const MAX = 200
  const trimmed = !expanded && text.length > MAX ? text.slice(0, MAX).trimEnd() + '…' : text
  return (
    <div style={{ borderTop: `2px solid ${color}`, padding: '12px 14px', background: `${color}07` }}>
      <div style={{ fontSize: 8, letterSpacing: 2.5, color, fontWeight: 700, marginBottom: 8 }}>{label}</div>
      <p style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.75, margin: 0 }}>{trimmed}</p>
      {text.length > MAX && (
        <button onClick={() => setExpanded(v => !v)} style={{
          marginTop: 8, background: 'none', border: 'none', cursor: 'pointer',
          fontSize: 9, color, letterSpacing: 1, fontFamily: 'inherit', padding: 0,
        }}>
          {expanded ? '▲ LESS' : '▼ MORE'}
        </button>
      )}
    </div>
  )
}

function EvidenceRow({ text, accent }) {
  return (
    <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '7px 10px',
      borderLeft: `2px solid ${accent}33`, background: `${accent}05` }}>
      <span style={{ width: 4, height: 4, borderRadius: '50%', background: accent,
        flexShrink: 0, marginTop: 5 }} />
      <span style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.6 }}>{text}</span>
    </div>
  )
}

function SectionLabel({ children, style }) {
  return (
    <div style={{ fontSize: 9, letterSpacing: 2.5, color: 'var(--text3)', fontWeight: 600,
      marginBottom: 10, textTransform: 'uppercase', ...style }}>
      {children}
    </div>
  )
}

function CommodityCard({ prediction: p }) {
  const isPos = (p.predicted_change_pct_high || 0) > 0
  const changeStr = p.predicted_change_pct_low != null
    ? `${isPos ? '+' : ''}${p.predicted_change_pct_low}% to ${isPos ? '+' : ''}${p.predicted_change_pct_high}%`
    : `${isPos ? '+' : ''}${p.predicted_change_pct || 0}%`
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
          <div style={{ fontSize: 18, fontWeight: 300, color: isPos ? 'var(--danger)' : 'var(--green)' }}>
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
        <div style={{ height: '100%', width: `${conf}%`, transition: 'width 1s ease',
          background: conf >= 70 ? 'var(--danger)' : conf >= 45 ? 'var(--warning)' : 'var(--text3)' }} />
      </div>
      {p.reasoning && (
        <div style={{ marginTop: 10, fontSize: 10, color: 'var(--text3)', lineHeight: 1.6 }}>
          {p.reasoning.slice(0, 120)}{p.reasoning.length > 120 ? '…' : ''}
        </div>
      )}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
    backdropFilter: 'blur(8px)', zIndex: 1000,
    display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24,
  },
  modal: {
    width: '100%', maxWidth: 880, maxHeight: '90vh',
    display: 'flex', flexDirection: 'column',
    background: '#070707', border: '1px solid rgba(255,255,255,0.1)',
    overflow: 'hidden',
  },
  header: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.07)', flexShrink: 0,
  },
  classification: {
    fontSize: 9, letterSpacing: 3, color: 'var(--danger)', marginBottom: 8, fontWeight: 600,
  },
  title: {
    fontSize: 18, fontWeight: 300, color: 'var(--text)', marginBottom: 8,
    lineHeight: 1.3, letterSpacing: -0.3,
  },
  metaLine: { fontSize: 10, color: 'var(--text3)', letterSpacing: 0.5 },
  closeBtn: {
    background: 'transparent', border: '1px solid rgba(255,255,255,0.1)',
    color: 'var(--text3)', width: 28, height: 28, cursor: 'pointer', fontSize: 12,
    fontFamily: 'inherit', display: 'flex', alignItems: 'center', justifyContent: 'center',
  },
  body: {
    flex: 1, overflowY: 'auto', padding: '20px 24px',
    display: 'flex', flexDirection: 'column',
  },
  assessSection: {
    marginBottom: 20,
  },
  summaryText: {
    fontSize: 13, color: 'var(--text2)', lineHeight: 1.85, fontWeight: 300, margin: 0,
  },
  threatText: {
    fontSize: 12, color: 'var(--text3)', lineHeight: 1.75, fontWeight: 300,
    margin: 0, borderTop: '1px solid rgba(255,255,255,0.05)',
    paddingTop: 12, marginTop: 12,
  },
  mlInterpNote: {
    fontSize: 10, color: 'var(--text3)', lineHeight: 1.7, fontStyle: 'italic',
    margin: '0 0 20px', paddingLeft: 2,
  },
  intelGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8,
  },
  predictionsGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8,
  },
  evidenceGrid: {
    display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24,
  },
  commodityCard: {
    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.07)',
    padding: '14px 16px',
  },
  actionCard: {
    display: 'flex', gap: 14, alignItems: 'flex-start',
    padding: '10px 14px',
    borderLeft: '2px solid rgba(0,229,255,0.4)',
    background: 'rgba(0,229,255,0.03)',
  },
  actionNum: {
    fontSize: 10, fontWeight: 700, color: 'var(--accent)',
    flexShrink: 0, width: 14, paddingTop: 2,
  },
  actionText: { fontSize: 12, color: 'var(--text2)', lineHeight: 1.65 },
  toggleBtn: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    width: '100%', background: 'none', border: 'none', cursor: 'pointer',
    padding: '0 0 10px', fontFamily: 'inherit',
  },
  reasoning: {
    fontSize: 11, color: 'var(--text3)', lineHeight: 1.9,
    background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)',
    padding: 14, fontStyle: 'italic', whiteSpace: 'pre-wrap',
    marginBottom: 16,
  },
  footer: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '14px 0 0', borderTop: '1px solid rgba(255,255,255,0.06)',
    marginTop: 'auto',
  },
  footerText: { fontSize: 9, color: 'var(--text3)', letterSpacing: 1 },
  downloadBtn: {
    background: 'transparent', border: '1px solid rgba(255,255,255,0.15)',
    color: 'var(--text2)', fontSize: 9, letterSpacing: 2, fontFamily: 'inherit',
    padding: '4px 12px', cursor: 'pointer', transition: 'border-color 0.15s, color 0.15s',
  },
}
