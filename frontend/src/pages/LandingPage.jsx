import { useEffect } from 'react'

const STATS = [
  { value: '1.1M+', label: 'SAR Detection Events' },
  { value: '39K',   label: 'Vessels Profiled' },
  { value: '14 mo', label: 'Historical Coverage' },
  { value: '3',     label: 'Critical Chokepoints' },
]

const CAPABILITIES = [
  {
    n: '01',
    title: 'Satellite Dark Vessel Detection',
    body: 'Sentinel-1 SAR radar identifies vessels operating without AIS — regardless of whether they want to be seen. Every disappearance is logged, dated, and precisely geolocated across 1.1 million events.',
  },
  {
    n: '02',
    title: 'Sanctions & Flag Screening',
    body: 'Instant cross-reference against OFAC, UN, EU, and UK sanctions lists. Flag-of-convenience mismatches flagged automatically across all 200+ jurisdictions.',
  },
  {
    n: '03',
    title: 'High-Risk Zone Exposure',
    body: 'Identify which critical chokepoints — Strait of Hormuz, Black Sea, Red Sea / Suez — a vessel has operated in, with detection counts, coordinates, and timestamps.',
  },
  {
    n: '04',
    title: 'AI Underwriting Reports',
    body: "Claude generates Lloyd's-grade underwriting assessments: risk score 0–100, premium loading recommendation, exclusion clauses, and peer benchmarking — in under 30 seconds.",
  },
]

const STEPS = [
  {
    n: '01',
    title: 'Search by MMSI',
    body: 'Enter any vessel MMSI. Pull its full satellite dark-event history, vessel identity record, and compliance status from a 39,000-vessel database.',
  },
  {
    n: '02',
    title: 'Instant Risk Score',
    body: 'Our engine scores the vessel 0–100 across sanctions exposure, zone activity, AIS dropout frequency, and peer comparison — in milliseconds.',
  },
  {
    n: '03',
    title: 'Generate AI Report',
    body: "One click produces a professional underwriting assessment ready for your records — downloadable as PDF. Premium loading, exclusion clauses, conditions, all included.",
  },
]

const ZONES = [
  {
    name: 'Strait of Hormuz',
    stat: '20%',
    label: 'of global oil supply transits this corridor',
    flag: 'Iran / UAE chokepoint',
    risk: 'CRITICAL',
  },
  {
    name: 'Red Sea / Suez',
    stat: '12%',
    label: 'of global trade volume passes through annually',
    flag: 'Active Houthi threat zone',
    risk: 'HIGH',
  },
  {
    name: 'Black Sea',
    stat: '30%',
    label: 'of European wheat supply originates here',
    flag: 'Active conflict zone',
    risk: 'HIGH',
  },
]

const RISK_COLORS = { CRITICAL: '#ff3355', HIGH: '#ff6b00' }

const DISPLAY = '"Barlow Condensed", "Barlow", system-ui, sans-serif'
const BODY    = '"Barlow", system-ui, -apple-system, sans-serif'

export default function LandingPage({ onEnter }) {
  useEffect(() => {
    const root = document.getElementById('root')
    const els = [document.documentElement, document.body, root]
    const prev = els.map(el => ({ overflow: el.style.overflow, height: el.style.height }))
    els.forEach(el => { el.style.overflow = 'auto'; el.style.height = 'auto' })
    return () => {
      els.forEach((el, i) => { el.style.overflow = prev[i].overflow; el.style.height = prev[i].height })
    }
  }, [])

  return (
    <div style={s.page}>

      {/* ── NAV ── */}
      <nav style={s.nav}>
        <span style={s.logo}>PELAGOS</span>
        <div style={s.navLinks}>
          <a href="#capabilities" style={s.navLink}>Capabilities</a>
          <a href="#workflow" style={s.navLink}>Workflow</a>
          <a href="#zones" style={s.navLink}>Risk Zones</a>
        </div>
        <button style={s.navCta} onClick={onEnter}>Launch Platform</button>
      </nav>

      {/* ── HERO ── */}
      <section style={s.hero}>
        <video
          autoPlay muted loop playsInline
          aria-hidden="true"
          style={s.heroBg}
          src="/hero-bg.mp4"
        />
        <div style={s.heroOverlay} aria-hidden="true" />
        <div style={s.heroGrid} aria-hidden="true" />
        <div style={s.heroInner}>
          <div style={s.heroEyebrow}>Maritime Intelligence · Insurance Underwriting</div>
          <h1 style={s.heroTitle}>
            Know Every<br />Vessel.
          </h1>
          <p style={s.heroSub}>
            Pelagos gives marine underwriters a complete picture of vessel behaviour,
            sanctions exposure, and satellite-detected dark activity — before they write the risk.
          </p>
          <div style={s.heroActions}>
            <button style={s.btnPrimary} onClick={onEnter}>Launch Platform</button>
            <a href="#capabilities" style={s.btnGhost}>See capabilities →</a>
          </div>
        </div>
        <div style={s.statsBar}>
          {STATS.map((st, i) => (
            <div key={st.label} style={{ ...s.statCell, borderLeft: i > 0 ? '1px solid rgba(255,255,255,0.08)' : 'none' }}>
              <span style={s.statNum}>{st.value}</span>
              <span style={s.statLbl}>{st.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── CAPABILITIES ── */}
      <section id="capabilities" style={s.section}>
        <div style={s.sectionHead}>
          <span style={s.eyebrow}>Capabilities</span>
          <h2 style={s.h2}>Everything an underwriter needs.<br />Nothing they don't.</h2>
        </div>
        <div>
          {CAPABILITIES.map(c => (
            <div key={c.n} style={s.row}>
              <span style={s.rowNum}>{c.n}</span>
              <div style={s.rowContent}>
                <div style={s.rowTitle}>{c.title}</div>
                <div style={s.rowBody}>{c.body}</div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── WORKFLOW ── */}
      <section id="workflow" style={s.sectionDark}>
        <div style={s.sectionDarkInner}>
          <div style={s.sectionHead}>
            <span style={s.eyebrow}>Workflow</span>
            <h2 style={s.h2}>From MMSI to report<br />in under 30 seconds.</h2>
          </div>
          <div style={{ marginBottom: 64 }}>
            {STEPS.map(st => (
              <div key={st.n} style={s.row}>
                <span style={s.rowNum}>{st.n}</span>
                <div style={s.rowContent}>
                  <div style={s.rowTitle}>{st.title}</div>
                  <div style={s.rowBody}>{st.body}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Terminal */}
          <div style={s.terminal}>
            <div style={s.termBar}>
              <span style={{ ...s.termDot, background: '#ff3355' }} />
              <span style={{ ...s.termDot, background: 'rgba(255,255,255,0.12)' }} />
              <span style={{ ...s.termDot, background: 'rgba(255,255,255,0.12)' }} />
              <span style={s.termBarLabel}>PELAGOS — VESSEL RISK ENGINE</span>
            </div>
            <pre style={s.termBody}>{[
              '> MMSI LOOKUP: 422143000',
              '',
              '  VESSEL     MARIVAN',
              '  FLAG       IRN (Iran) — SANCTIONED ⚠',
              '  OWNER      NITC (National Iranian Tanker Company)',
              '  LENGTH     320 m  |  TONNAGE  300,000 GT',
              '',
              '  DARK EVENTS    14',
              '  ZONE EXPOSURE  Strait of Hormuz ×11, Persian Gulf ×3',
              '',
              '  RISK SCORE     78 / 100  [CRITICAL]',
              '  PREMIUM        +65% above standard rate',
              '  RECOMMENDATION Decline or require war-risk exclusion',
              '',
              '> GENERATING AI UNDERWRITING REPORT...  ✓',
            ].join('\n')}</pre>
          </div>

          <div style={{ marginTop: 32, textAlign: 'center' }}>
            <button style={s.btnPrimary} onClick={onEnter}>Try it with MMSI 422143000 →</button>
          </div>
        </div>
      </section>

      {/* ── RISK ZONES ── */}
      <section id="zones" style={s.section}>
        <div style={s.sectionHead}>
          <span style={s.eyebrow}>Risk Zones</span>
          <h2 style={s.h2}>The world's most critical<br />maritime chokepoints.</h2>
        </div>
        <div style={s.table}>
          <div style={s.tableHead}>
            <span>Zone</span>
            <span>Exposure</span>
            <span>Classification</span>
            <span style={{ textAlign: 'right' }}>Risk</span>
          </div>
          {ZONES.map(z => (
            <div key={z.name} style={s.tableRow}>
              <span style={s.tZone}>{z.name}</span>
              <span style={s.tStat}><strong style={{ color: '#fff', fontWeight: 600 }}>{z.stat}</strong> — {z.label}</span>
              <span style={s.tFlag}>{z.flag}</span>
              <span style={{ ...s.tRisk, color: RISK_COLORS[z.risk] }}>● {z.risk}</span>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section style={s.ctaSection}>
        <h2 style={s.ctaTitle}>Start underwriting<br />with confidence.</h2>
        <p style={s.ctaSub}>
          Powered by Sentinel-1 satellite intelligence and Anthropic Claude.<br />
          Search any vessel. Score the risk. Generate a Lloyd's-grade report.
        </p>
        <button style={s.btnPrimary} onClick={onEnter}>Launch Pelagos →</button>
      </section>

      {/* ── FOOTER ── */}
      <footer style={s.footer}>
        <span style={s.logo}>PELAGOS</span>
        <span style={s.footerMeta}>
          SAR Data: Global Fishing Watch · AI: Anthropic Claude · Mapping: Mapbox
        </span>
      </footer>

    </div>
  )
}

const s = {
  page: {
    background: '#000', color: '#fff',
    fontFamily: BODY, overflowX: 'hidden',
  },

  nav: {
    position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0 48px', height: 72,
    background: '#000',
    borderBottom: '1px solid rgba(255,255,255,0.1)',
  },
  logo: {
    fontFamily: DISPLAY, fontSize: 18, fontWeight: 700,
    letterSpacing: 4, color: '#fff', textTransform: 'uppercase',
  },
  navLinks: { display: 'flex', gap: 40 },
  navLink: {
    color: 'rgba(255,255,255,0.45)', fontSize: 14,
    textDecoration: 'none', letterSpacing: 0.2,
  },
  navCta: {
    background: '#fff', color: '#000', border: 'none',
    padding: '9px 22px', fontSize: 13, fontWeight: 600,
    letterSpacing: 0.3, cursor: 'pointer', fontFamily: BODY,
  },

  hero: {
    minHeight: '100vh', display: 'flex', flexDirection: 'column',
    justifyContent: 'center', paddingTop: 60,
    position: 'relative', overflow: 'hidden',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
  },
  heroBg: {
    position: 'absolute', inset: 0, width: '100%', height: '100%',
    objectFit: 'cover', objectPosition: 'center',
    pointerEvents: 'none', zIndex: 0,
  },
  heroOverlay: {
    position: 'absolute', inset: 0, zIndex: 1,
    background: 'linear-gradient(to bottom, rgba(0,0,0,0.72) 0%, rgba(0,0,0,0.55) 60%, rgba(0,0,0,0.85) 100%)',
    pointerEvents: 'none',
  },
  heroGrid: {
    position: 'absolute', inset: 0,
    backgroundImage: [
      'linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px)',
      'linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px)',
    ].join(', '),
    backgroundSize: '80px 80px',
    pointerEvents: 'none', zIndex: 2,
  },
  heroInner: {
    maxWidth: 1100, margin: '0 auto',
    padding: '100px 48px 64px',
    position: 'relative', zIndex: 2,
  },
  heroEyebrow: {
    fontSize: 11, letterSpacing: 3,
    color: 'rgba(255,255,255,0.35)', textTransform: 'uppercase',
    marginBottom: 36, fontFamily: BODY,
  },
  heroTitle: {
    fontFamily: DISPLAY,
    fontSize: 'clamp(72px, 11vw, 132px)',
    fontWeight: 800, lineHeight: 0.92,
    letterSpacing: -3, color: '#fff',
    margin: '0 0 44px',
  },
  heroSub: {
    fontSize: 'clamp(15px, 1.4vw, 18px)',
    color: 'rgba(255,255,255,0.5)', lineHeight: 1.65,
    maxWidth: 520, margin: '0 0 52px', fontWeight: 400,
  },
  heroActions: { display: 'flex', gap: 24, alignItems: 'center' },

  statsBar: {
    display: 'flex',
    borderTop: '1px solid rgba(255,255,255,0.08)',
    position: 'relative', zIndex: 2,
  },
  statCell: {
    flex: 1, padding: '32px 48px',
    display: 'flex', flexDirection: 'column', gap: 6,
  },
  statNum: {
    fontFamily: DISPLAY, fontSize: 40, fontWeight: 700,
    color: '#fff', letterSpacing: -1, lineHeight: 1,
  },
  statLbl: {
    fontSize: 11, color: 'rgba(255,255,255,0.35)',
    letterSpacing: 1.5, textTransform: 'uppercase',
  },

  btnPrimary: {
    background: '#fff', color: '#000', border: 'none',
    padding: '14px 32px', fontSize: 14, fontWeight: 700,
    letterSpacing: 0.3, cursor: 'pointer', fontFamily: BODY,
  },
  btnGhost: {
    color: 'rgba(255,255,255,0.45)', fontSize: 14,
    textDecoration: 'none', letterSpacing: 0.2,
  },

  section: {
    maxWidth: 1100, margin: '0 auto',
    padding: '100px 48px',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  sectionDark: {
    background: '#080808',
    borderTop: '1px solid rgba(255,255,255,0.06)',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  sectionDarkInner: {
    maxWidth: 1100, margin: '0 auto', padding: '100px 48px',
  },
  sectionHead: { marginBottom: 64 },
  eyebrow: {
    display: 'block', fontSize: 11, letterSpacing: 3,
    color: 'rgba(255,255,255,0.3)', textTransform: 'uppercase',
    marginBottom: 20, fontFamily: BODY,
  },
  h2: {
    fontFamily: DISPLAY,
    fontSize: 'clamp(32px, 4.5vw, 60px)',
    fontWeight: 700, lineHeight: 1.0,
    letterSpacing: -1.5, color: '#fff', margin: 0,
  },

  row: {
    display: 'flex', gap: 48, padding: '32px 0',
    borderTop: '1px solid rgba(255,255,255,0.06)',
    alignItems: 'flex-start',
  },
  rowNum: {
    fontFamily: DISPLAY, fontSize: 12, fontWeight: 600,
    color: 'rgba(255,255,255,0.2)', letterSpacing: 1.5,
    flexShrink: 0, width: 28, paddingTop: 4,
  },
  rowContent: { flex: 1 },
  rowTitle: {
    fontSize: 17, fontWeight: 600, color: '#fff',
    marginBottom: 10, letterSpacing: -0.2,
  },
  rowBody: {
    fontSize: 14, color: 'rgba(255,255,255,0.45)',
    lineHeight: 1.75, maxWidth: 680,
  },

  terminal: {
    border: '1px solid rgba(255,255,255,0.1)',
    background: '#000', overflow: 'hidden',
  },
  termBar: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '12px 20px', background: '#0d0d0d',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  termDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0 },
  termBarLabel: {
    fontSize: 10, color: 'rgba(255,255,255,0.25)',
    letterSpacing: 2, marginLeft: 8,
    fontFamily: '"SF Mono","Fira Code","Roboto Mono",monospace',
  },
  termBody: {
    padding: '32px 28px',
    fontFamily: '"SF Mono","Fira Code","Roboto Mono",monospace',
    fontSize: 12.5, color: 'rgba(255,255,255,0.75)',
    lineHeight: 1.85, margin: 0,
    whiteSpace: 'pre', overflowX: 'auto',
  },

  table: { display: 'flex', flexDirection: 'column' },
  tableHead: {
    display: 'grid', gridTemplateColumns: '1.6fr 2.4fr 1.4fr 0.8fr',
    padding: '10px 0 14px',
    borderBottom: '1px solid rgba(255,255,255,0.15)',
    fontSize: 10, letterSpacing: 2,
    color: 'rgba(255,255,255,0.25)', textTransform: 'uppercase',
  },
  tableRow: {
    display: 'grid', gridTemplateColumns: '1.6fr 2.4fr 1.4fr 0.8fr',
    padding: '26px 0',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
    alignItems: 'center',
  },
  tZone:  { fontSize: 16, fontWeight: 600, color: '#fff' },
  tStat:  { fontSize: 13, color: 'rgba(255,255,255,0.45)' },
  tFlag:  { fontSize: 11, color: 'rgba(255,255,255,0.3)', letterSpacing: 0.3 },
  tRisk:  { fontSize: 11, letterSpacing: 1.5, fontWeight: 600, textAlign: 'right' },

  ctaSection: {
    padding: '140px 48px', textAlign: 'center',
    borderBottom: '1px solid rgba(255,255,255,0.06)',
  },
  ctaTitle: {
    fontFamily: DISPLAY,
    fontSize: 'clamp(52px, 9vw, 108px)',
    fontWeight: 800, lineHeight: 0.92, letterSpacing: -3,
    margin: '0 0 36px', color: '#fff',
  },
  ctaSub: {
    fontSize: 16, color: 'rgba(255,255,255,0.4)',
    lineHeight: 1.65, margin: '0 auto 52px', maxWidth: 480,
  },

  footer: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '28px 48px',
  },
  footerMeta: {
    fontSize: 11, color: 'rgba(255,255,255,0.2)', letterSpacing: 0.3,
  },
}
