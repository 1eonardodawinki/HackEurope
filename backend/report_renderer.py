"""
Generates a PDF from a report dict using ReportLab (no LaTeX required).

Also exposes render_latex() for legacy use or manual compilation.
"""

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.platypus.flowables import Flowable

# ── Colour palette (mirrors the LaTeX version) ────────────────────────────────

C_DANGER  = colors.Color(155/255, 20/255,  20/255)
C_WARN    = colors.Color(150/255, 85/255,   0/255)
C_GREEN   = colors.Color( 20/255,105/255,  45/255)
C_ACCENT  = colors.Color(  0/255, 75/255, 155/255)
C_MID     = colors.Color( 90/255, 90/255,  90/255)
C_LIGHT   = colors.Color(160/255,160/255, 160/255)
C_RULE    = colors.Color(210/255,210/255, 210/255)
C_DARK    = colors.Color( 20/255, 20/255,  20/255)
C_BG_HEAD = colors.Color(240/255,243/255,248/255)

TIER_COLOR = {"HIGH": C_DANGER, "MEDIUM": C_WARN, "LOW": C_GREEN}

PAGE_W, PAGE_H = A4
MARGIN = 2.2 * cm


# ── Styles ─────────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "classification": S(
            "classification",
            fontName="Helvetica-Bold",
            fontSize=7,
            textColor=C_DANGER,
            alignment=TA_CENTER,
            spaceAfter=3,
        ),
        "title": S(
            "title",
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=C_DARK,
            alignment=TA_CENTER,
            spaceAfter=3,
        ),
        "subtitle": S(
            "subtitle",
            fontName="Helvetica",
            fontSize=8,
            textColor=C_MID,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "section": S(
            "section",
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=C_MID,
            spaceBefore=14,
            spaceAfter=5,
            leading=10,
        ),
        "body": S(
            "body",
            fontName="Helvetica",
            fontSize=9,
            textColor=C_DARK,
            leading=13,
            spaceAfter=4,
        ),
        "body_italic": S(
            "body_italic",
            fontName="Helvetica-Oblique",
            fontSize=8.5,
            textColor=C_MID,
            leading=13,
            spaceAfter=4,
        ),
        "small": S(
            "small",
            fontName="Helvetica",
            fontSize=7.5,
            textColor=C_MID,
            leading=11,
        ),
        "footer": S(
            "footer",
            fontName="Helvetica",
            fontSize=6.5,
            textColor=C_LIGHT,
            alignment=TA_CENTER,
        ),
        "threat": S(
            "threat",
            fontName="Helvetica",
            fontSize=9,
            textColor=C_MID,
            leading=13,
            spaceAfter=4,
        ),
        "bullet": S(
            "bullet",
            fontName="Helvetica",
            fontSize=8.5,
            textColor=C_DARK,
            leading=12,
            leftIndent=12,
            spaceAfter=2,
            bulletIndent=0,
        ),
    }


# ── Page template with header/footer ─────────────────────────────────────────

class _HeaderFooterCanvas:
    """Mixin-style: applied via onPage callback."""

    def __init__(self, canvas, doc, now: str):
        self.canvas = canvas
        self.doc = doc
        self.now = now

    def draw(self):
        c = self.canvas
        w, h = A4
        c.saveState()

        # Header rule
        c.setStrokeColor(C_RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN, h - 1.2 * cm, w - MARGIN, h - 1.2 * cm)

        # Header text
        c.setFont("Helvetica", 6.5)
        c.setFillColor(C_LIGHT)
        c.drawString(MARGIN, h - 1.0 * cm, "INTELLIGENCE REPORT — RESTRICTED")
        c.drawRightString(w - MARGIN, h - 1.0 * cm, "MARITIME SENTINEL — BALAGAER INTELLIGENCE")

        # Footer rule
        c.line(MARGIN, 1.35 * cm, w - MARGIN, 1.35 * cm)

        # Footer text
        c.drawCentredString(w / 2, 0.85 * cm, f"Page {self.doc.page}")

        c.restoreState()


# ── Helper: bullet list ───────────────────────────────────────────────────────

def _bullet_list(items: list, styles: dict) -> list:
    out = []
    for item in items:
        out.append(Paragraph(f"– {item}", styles["bullet"]))
    return out


def _numbered_list(items: list, styles: dict) -> list:
    out = []
    for i, item in enumerate(items, 1):
        out.append(Paragraph(f"{i}. {item}", styles["bullet"]))
    return out


# ── Helper: section header ────────────────────────────────────────────────────

def _section(title: str, styles: dict) -> list:
    return [
        Paragraph(title.upper(), styles["section"]),
        HRFlowable(width="100%", thickness=0.5, color=C_RULE, spaceAfter=4),
    ]


# ── Helper: coloured tag ──────────────────────────────────────────────────────

def _tag(text: str, color=C_MID) -> str:
    hex_c = "#{:02X}{:02X}{:02X}".format(
        int(color.red * 255), int(color.green * 255), int(color.blue * 255)
    )
    return f'<font color="{hex_c}"><b>{text}</b></font>'


# ── Main PDF renderer ─────────────────────────────────────────────────────────

def render_pdf(report: dict) -> bytes:
    """Return a PDF as bytes from a report dict."""

    meta    = report.get("_meta", {})
    is_inv  = "ml_risk_score" in report
    ml      = report.get("ml_risk_score") or {}
    now     = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    styles  = _build_styles()

    title    = report.get("title", "Maritime Intelligence Assessment")
    cls_str  = report.get("classification", "INTELLIGENCE REPORT - RESTRICTED")
    exec_sum = report.get("executive_summary", "")
    threat   = report.get("threat_assessment", "")
    cot      = report.get("chain_of_thought", "")

    evidence    = report.get("supporting_evidence", []) or []
    risks       = report.get("risk_factors", []) or []
    actions     = report.get("recommended_actions", []) or []
    predictions = report.get("commodity_predictions", []) or []

    ml_pct   = int((ml.get("probability", 0)) * 100)
    tier     = ml.get("risk_tier", "UNKNOWN")
    conf     = report.get("overall_confidence")
    approved = meta.get("final_approved", False)
    tier_clr = TIER_COLOR.get(tier, C_MID)

    conf_str    = f"{conf}%" if conf is not None else "—"
    status_str  = "APPROVED" if approved else "PROVISIONAL"
    status_clr  = C_GREEN if approved else C_WARN

    # ── Buffer & document ─────────────────────────────────────────────────────
    buf = io.BytesIO()

    def _on_page(canvas, doc):
        _HeaderFooterCanvas(canvas, doc, now).draw()

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=1.6 * cm,
        bottomMargin=1.8 * cm,
        title=title,
        author="BALAGAER Intelligence Platform",
    )
    frame = Frame(
        MARGIN, 1.8 * cm,
        PAGE_W - 2 * MARGIN, PAGE_H - 1.6 * cm - 1.8 * cm,
        id="main",
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_on_page)])

    story = []

    # ── Title block ───────────────────────────────────────────────────────────
    story.append(Paragraph(cls_str.upper(), styles["classification"]))
    story.append(Paragraph(title, styles["title"]))
    story.append(Paragraph(
        f"BALAGAER Intelligence Monitoring Platform  •  Generated {now}",
        styles["subtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=0.8, color=C_ACCENT, spaceAfter=8))

    # ── Meta bar ──────────────────────────────────────────────────────────────
    if is_inv:
        mmsi_val = str(meta.get("mmsi", ml.get("mmsi", "—")))
        tier_html = _tag(f"{ml_pct}% {tier}", tier_clr)
        meta_data = [
            [
                Paragraph("<b>MMSI</b>", styles["small"]),
                Paragraph("<b>ML RISK</b>", styles["small"]),
                Paragraph("<b>CONFIDENCE</b>", styles["small"]),
                Paragraph("<b>STATUS</b>", styles["small"]),
            ],
            [
                Paragraph(mmsi_val, styles["small"]),
                Paragraph(tier_html, styles["small"]),
                Paragraph(conf_str, styles["small"]),
                Paragraph(_tag(status_str, status_clr), styles["small"]),
            ],
        ]
    else:
        region_val  = str(meta.get("region", "—"))
        inc_count   = str(int(meta.get("incident_count", 0)))
        meta_data = [
            [
                Paragraph("<b>REGION</b>", styles["small"]),
                Paragraph("<b>INCIDENTS</b>", styles["small"]),
                Paragraph("<b>CONFIDENCE</b>", styles["small"]),
                Paragraph("<b>STATUS</b>", styles["small"]),
            ],
            [
                Paragraph(region_val, styles["small"]),
                Paragraph(inc_count, styles["small"]),
                Paragraph(conf_str, styles["small"]),
                Paragraph(_tag(status_str, status_clr), styles["small"]),
            ],
        ]

    col_w = (PAGE_W - 2 * MARGIN) / 4
    meta_tbl = Table(meta_data, colWidths=[col_w] * 4, hAlign="LEFT")
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_BG_HEAD),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
        ("BOX",       (0, 0), (-1, -1), 0.5, C_RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, C_RULE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    # ── Assessment ────────────────────────────────────────────────────────────
    story.extend(_section("Assessment", styles))
    if exec_sum:
        story.append(Paragraph(exec_sum, styles["body"]))
    if threat and threat != exec_sum:
        story.append(Paragraph(threat, styles["threat"]))

    # ── ML score (investigation only) ─────────────────────────────────────────
    if is_inv:
        interp = ml.get("interpretation", "")
        if interp:
            tier_html = _tag(f"{ml_pct}% {tier}", tier_clr)
            story.append(Paragraph(
                f'{_tag("ML Score:", C_MID)} {tier_html} — <i>{interp}</i>',
                styles["body"],
            ))

    # ── Intel sources (investigation only) ────────────────────────────────────
    if is_inv:
        news_txt = report.get("news_intelligence", "") or ""
        sanc_txt = report.get("sanctions_assessment", "") or ""
        geo_txt  = report.get("geopolitical_context", "") or ""
        if news_txt or sanc_txt or geo_txt:
            def _cell(t, limit=350):
                return (t[:limit] + "…") if len(t) > limit else t

            story.extend(_section("Intelligence Sources", styles))
            src_data = [
                [
                    Paragraph(_tag("NEWS", C_ACCENT), styles["small"]),
                    Paragraph(_tag("SANCTIONS", C_WARN), styles["small"]),
                    Paragraph(_tag("GEOPOLITICAL", C_DANGER), styles["small"]),
                ],
                [
                    Paragraph(_cell(news_txt), styles["small"]),
                    Paragraph(_cell(sanc_txt), styles["small"]),
                    Paragraph(_cell(geo_txt),  styles["small"]),
                ],
            ]
            col3 = (PAGE_W - 2 * MARGIN) / 3
            src_tbl = Table(src_data, colWidths=[col3, col3, col3], hAlign="LEFT")
            src_tbl.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), C_BG_HEAD),
                ("BOX",       (0, 0), (-1, -1), 0.5, C_RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, C_RULE),
                ("VALIGN",    (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",    (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ]))
            story.append(src_tbl)

    # ── Evidence + Risk factors ────────────────────────────────────────────────
    if evidence or risks:
        story.extend(_section("Evidence and Risk Factors", styles))
        usable_w = PAGE_W - 2 * MARGIN

        if evidence and risks:
            ev_col = [Paragraph("<b>Supporting Evidence</b>", styles["small"])] + _bullet_list(evidence, styles)
            ri_col = [Paragraph("<b>Risk Factors</b>", styles["small"])] + _bullet_list(risks, styles)
            half = usable_w / 2 - 4
            ev_tbl = Table(
                [[ev_col, ri_col]],
                colWidths=[half, half],
                hAlign="LEFT",
            )
            ev_tbl.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(ev_tbl)
        elif evidence:
            story.append(Paragraph("<b>Supporting Evidence</b>", styles["small"]))
            story.extend(_bullet_list(evidence, styles))
        else:
            story.append(Paragraph("<b>Risk Factors</b>", styles["small"]))
            story.extend(_bullet_list(risks, styles))

    # ── Recommended Actions (investigation only) ──────────────────────────────
    if is_inv and actions:
        story.extend(_section("Recommended Actions", styles))
        story.extend(_numbered_list(actions, styles))

    # ── Commodity Predictions (standard reports) ───────────────────────────────
    if predictions:
        story.extend(_section("Commodity Market Impact Forecast", styles))
        header = [
            Paragraph("<b>Commodity</b>", styles["small"]),
            Paragraph("<b>Current</b>", styles["small"]),
            Paragraph("<b>Forecast</b>", styles["small"]),
            Paragraph("<b>Timeframe</b>", styles["small"]),
            Paragraph("<b>Conf.</b>", styles["small"]),
        ]
        rows = [header]
        for p in predictions:
            hi   = p.get("predicted_change_pct_high", 0) or 0
            lo   = p.get("predicted_change_pct_low", hi) or hi
            sign = "+" if hi > 0 else ""
            pct  = f"{sign}{lo}%–{sign}{hi}%" if lo != hi else f"{sign}{hi}%"
            clr  = C_DANGER if hi > 0 else C_GREEN
            rows.append([
                Paragraph(str(p.get("commodity", "")), styles["small"]),
                Paragraph(str(p.get("current_price", "")), styles["small"]),
                Paragraph(_tag(pct, clr), styles["small"]),
                Paragraph(str(p.get("timeframe", "")), styles["small"]),
                Paragraph(f"{p.get('confidence', 0)}%", styles["small"]),
            ])
        col_w = (PAGE_W - 2 * MARGIN)
        pred_tbl = Table(
            rows,
            colWidths=[col_w * 0.28, col_w * 0.14, col_w * 0.18, col_w * 0.24, col_w * 0.16],
            hAlign="LEFT",
            repeatRows=1,
        )
        pred_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_BG_HEAD),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
            ("BOX",       (0, 0), (-1, -1), 0.5, C_RULE),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, C_RULE),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ]))
        story.append(pred_tbl)

    # ── Analyst Reasoning ─────────────────────────────────────────────────────
    if cot:
        story.extend(_section("Analyst Reasoning", styles))
        story.append(Paragraph(cot, styles["body_italic"]))

    # ── Footer line ───────────────────────────────────────────────────────────
    critic_rounds = meta.get("critic_rounds", 1)
    quality       = meta.get("critic_quality_score", "—")
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.4, color=C_RULE, spaceAfter=4))
    story.append(Paragraph(
        f"Classification: {cls_str}  •  Critic rounds: {critic_rounds}  •  "
        f"Quality: {quality}/100  •  Model: Claude Haiku 4.5  •  Platform: BALAGAER Intelligence",
        styles["footer"],
    ))

    doc.build(story)
    return buf.getvalue()


# ── Legacy LaTeX renderer (kept for reference / manual compilation) ───────────

def _esc(s) -> str:
    """Escape LaTeX special characters in a string."""
    if s is None:
        return ''
    s = str(s)
    s = s.replace('\\', 'XXBSXX')
    s = s.replace('&',  r'\&')
    s = s.replace('%',  r'\%')
    s = s.replace('$',  r'\$')
    s = s.replace('#',  r'\#')
    s = s.replace('_',  r'\_')
    s = s.replace('{',  r'\{')
    s = s.replace('}',  r'\}')
    s = s.replace('~',  r'\textasciitilde{}')
    s = s.replace('^',  r'\textasciicircum{}')
    s = s.replace('XXBSXX', r'\textbackslash{}')
    return s


def render_latex(report: dict) -> str:
    """Return LaTeX source. Compile with pdflatex for a PDF."""
    meta   = report.get('_meta', {})
    is_inv = 'ml_risk_score' in report
    ml     = report.get('ml_risk_score') or {}
    now    = datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')

    title    = _esc(report.get('title', 'Maritime Intelligence Assessment'))
    cls_str  = _esc(report.get('classification', 'INTELLIGENCE REPORT - RESTRICTED'))
    exec_sum = _esc(report.get('executive_summary', ''))
    threat   = _esc(report.get('threat_assessment', ''))
    cot      = _esc(report.get('chain_of_thought', ''))

    evidence    = report.get('supporting_evidence', [])
    risks       = report.get('risk_factors', [])
    actions     = report.get('recommended_actions', [])
    predictions = report.get('commodity_predictions', [])

    ml_pct = int((ml.get('probability', 0)) * 100)
    tier   = ml.get('risk_tier', 'UNKNOWN')
    conf   = report.get('overall_confidence')
    approved = meta.get('final_approved', False)

    tier_color = {'HIGH': 'C-danger', 'MEDIUM': 'C-warn', 'LOW': 'C-green'}.get(tier, 'C-mid')

    def _itemize(items):
        if not items:
            return ''
        inner = '\n'.join(f'  \\item {_esc(x)}' for x in items)
        return f'\\begin{{itemize}}\n{inner}\n\\end{{itemize}}'

    def _enumerate_list(items):
        if not items:
            return ''
        inner = '\n'.join(f'  \\item {_esc(x)}' for x in items)
        return f'\\begin{{enumerate}}\n{inner}\n\\end{{enumerate}}'

    out = []
    out.append(r"""
\documentclass[10pt,a4paper]{article}
\usepackage[margin=2.2cm,top=1.8cm,bottom=1.8cm,headheight=14pt]{geometry}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage[dvipsnames]{xcolor}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{microtype}
\usepackage{parskip}
\usepackage{booktabs}
\usepackage{tabularx}

\definecolor{C-mid}{RGB}{90,90,90}
\definecolor{C-light}{RGB}{160,160,160}
\definecolor{C-rule}{RGB}{210,210,210}
\definecolor{C-danger}{RGB}{155,20,20}
\definecolor{C-warn}{RGB}{150,85,0}
\definecolor{C-green}{RGB}{20,105,45}
\definecolor{C-accent}{RGB}{0,75,155}

\setlength{\parskip}{5pt}
\setlength{\parindent}{0pt}

\titleformat{\section}
  {\normalfont\scriptsize\bfseries\color{C-mid}\MakeUppercase}
  {}{0em}{}[\vspace{1pt}{\color{C-rule}\titlerule}]
\titlespacing{\section}{0pt}{16pt}{8pt}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\tiny\textcolor{C-light}{INTELLIGENCE REPORT --- RESTRICTED}}
\fancyhead[R]{\tiny\textcolor{C-light}{BALAGAER INTELLIGENCE PLATFORM}}
\fancyfoot[C]{\tiny\textcolor{C-light}{\thepage}}
\renewcommand{\headrulewidth}{0.3pt}
\renewcommand{\headrule}{\color{C-rule}\hrule width\headwidth height\headrulewidth}

\setlist[itemize]{leftmargin=12pt,itemsep=2pt,topsep=3pt,parsep=0pt,label=\textendash}
\setlist[enumerate]{leftmargin=16pt,itemsep=2pt,topsep=3pt,parsep=0pt}

\begin{document}
""")

    out.append(f"""{{\\centering
  {{\\tiny\\textcolor{{C-danger}}{{\\textbf{{{cls_str}}}}}}}\\\\[5pt]
  {{\\Large\\textbf{{{title}}}}}\\\\[4pt]
  {{\\scriptsize\\textcolor{{C-mid}}{{BALAGAER Intelligence Monitoring Platform\\quad\\textbullet\\quad Generated {now}}}}}\\par}}
\\vspace{{5pt}}{{\\color{{C-rule}}\\rule{{\\textwidth}}{{0.5pt}}}}\\vspace{{5pt}}
""")

    approved_latex = (
        r'{\color{C-green}\textbf{APPROVED}}'
        if approved else r'{\color{C-warn}PROVISIONAL}'
    )
    conf_str = f'{conf}\\%' if conf is not None else '---'

    if is_inv:
        mmsi_str = _esc(str(meta.get('mmsi', ml.get('mmsi', '---'))))
        out.append(
            f"\\begin{{tabular}}{{@{{}}p{{0.22\\textwidth}}p{{0.22\\textwidth}}"
            f"p{{0.22\\textwidth}}p{{0.34\\textwidth}}@{{}}}}\n"
            f"  {{\\small\\textbf{{MMSI}}}} & {{\\small\\textbf{{ML RISK}}}} & "
            f"{{\\small\\textbf{{CONFIDENCE}}}} & {{\\small\\textbf{{STATUS}}}}\\\\\n"
            f"  {{\\scriptsize {mmsi_str}}} & "
            f"{{\\scriptsize\\textcolor{{{tier_color}}}{{{ml_pct}\\% {tier}}}}} & "
            f"{{\\scriptsize {conf_str}}} & {{\\scriptsize {approved_latex}}}\\\\\n"
            f"\\end{{tabular}}\n"
        )
    else:
        region_str = _esc(str(meta.get('region', '---')))
        inc_count  = int(meta.get('incident_count', 0))
        out.append(
            f"\\begin{{tabular}}{{@{{}}p{{0.22\\textwidth}}p{{0.22\\textwidth}}"
            f"p{{0.22\\textwidth}}p{{0.34\\textwidth}}@{{}}}}\n"
            f"  {{\\small\\textbf{{REGION}}}} & {{\\small\\textbf{{INCIDENTS}}}} & "
            f"{{\\small\\textbf{{CONFIDENCE}}}} & {{\\small\\textbf{{STATUS}}}}\\\\\n"
            f"  {{\\scriptsize {region_str}}} & {{\\scriptsize {inc_count}}} & "
            f"{{\\scriptsize {conf_str}}} & {{\\scriptsize {approved_latex}}}\\\\\n"
            f"\\end{{tabular}}\n"
        )

    out.append("\\vspace{5pt}{\\color{C-rule}\\rule{\\textwidth}{0.3pt}}\n")
    out.append("\\section{Assessment}\n")
    out.append(exec_sum + "\n\n")
    if threat and threat != exec_sum:
        out.append(f"\\textcolor{{C-mid}}{{{threat}}}\n\n")

    if is_inv:
        interp = _esc(ml.get('interpretation', ''))
        if interp:
            out.append(
                f"\\noindent\\textcolor{{C-mid}}{{\\textbf{{ML Score:}}}}\\ "
                f"\\textcolor{{{tier_color}}}{{{ml_pct}\\% {tier}}}"
                f" --- {{\\small\\textit{{{interp}}}}}\n\n"
            )

    if is_inv:
        news_txt = _esc(report.get('news_intelligence', ''))
        sanc_txt = _esc(report.get('sanctions_assessment', ''))
        geo_txt  = _esc(report.get('geopolitical_context', ''))
        if news_txt or sanc_txt or geo_txt:
            def _cell(t, limit=380):
                return (t[:limit] + r'\ldots') if len(t) > limit else t
            out.append("\\section{Intelligence Sources}\n")
            out.append(
                f"\\begin{{tabularx}}{{\\textwidth}}{{@{{}}XXX@{{}}}}\n"
                f"  \\toprule\n"
                f"  {{\\scriptsize\\textcolor{{C-accent}}{{\\textbf{{NEWS}}}}}} &\n"
                f"  {{\\scriptsize\\textcolor{{C-warn}}{{\\textbf{{SANCTIONS}}}}}} &\n"
                f"  {{\\scriptsize\\textcolor{{C-danger}}{{\\textbf{{GEOPOLITICAL}}}}}}\\\\\n"
                f"  \\midrule\n"
                f"  {{\\scriptsize {_cell(news_txt)}}} &\n"
                f"  {{\\scriptsize {_cell(sanc_txt)}}} &\n"
                f"  {{\\scriptsize {_cell(geo_txt)}}}\\\\\n"
                f"  \\bottomrule\n"
                f"\\end{{tabularx}}\n"
            )

    if evidence or risks:
        out.append("\\section{Evidence and Risk Factors}\n")
        if evidence and risks:
            ev_items = '\n'.join(f'  \\item {_esc(e)}' for e in evidence)
            ri_items = '\n'.join(f'  \\item {_esc(r)}' for r in risks)
            out.append(
                f"\\noindent\\begin{{minipage}}[t]{{0.48\\textwidth}}\n"
                f"  {{\\small\\textbf{{Supporting Evidence}}}}\n"
                f"  \\begin{{itemize}}\n{ev_items}\n  \\end{{itemize}}\n"
                f"\\end{{minipage}}\n"
                f"\\hfill\n"
                f"\\begin{{minipage}}[t]{{0.48\\textwidth}}\n"
                f"  {{\\small\\textbf{{Risk Factors}}}}\n"
                f"  \\begin{{itemize}}\n{ri_items}\n  \\end{{itemize}}\n"
                f"\\end{{minipage}}\n"
            )
        elif evidence:
            out.append("\\textbf{Supporting Evidence}\n" + _itemize(evidence) + "\n")
        else:
            out.append("\\textbf{Risk Factors}\n" + _itemize(risks) + "\n")

    if is_inv and actions:
        out.append("\\section{Recommended Actions}\n")
        out.append(_enumerate_list(actions) + "\n")

    if predictions:
        out.append("\\section{Commodity Market Impact Forecast}\n")
        rows = []
        for p in predictions:
            hi   = p.get('predicted_change_pct_high', 0) or 0
            lo   = p.get('predicted_change_pct_low', hi) or hi
            sign = '+' if hi > 0 else ''
            pct  = f'{sign}{lo}\\%--{sign}{hi}\\%' if lo != hi else f'{sign}{hi}\\%'
            clr  = 'C-danger' if hi > 0 else 'C-green'
            rows.append(
                f"  {_esc(p.get('commodity', ''))} & "
                f"{_esc(str(p.get('current_price', '')))} & "
                f"\\textcolor{{{clr}}}{{{pct}}} & "
                f"{_esc(p.get('timeframe', ''))} & "
                f"{p.get('confidence', 0)}\\% \\\\"
            )
        out.append(
            f"\\begin{{tabularx}}{{\\textwidth}}{{@{{}}l r r l r@{{}}}}\n"
            f"  \\toprule\n"
            f"  \\textbf{{Commodity}} & \\textbf{{Current}} & \\textbf{{Forecast}} & "
            f"\\textbf{{Timeframe}} & \\textbf{{Conf.}}\\\\\n"
            f"  \\midrule\n"
            + '\n'.join(rows) + "\n"
            f"  \\bottomrule\n"
            f"\\end{{tabularx}}\n"
        )

    if cot:
        out.append("\\section{Analyst Reasoning}\n")
        out.append(f"\\begin{{small}}\n\\textit{{{cot}}}\n\\end{{small}}\n\n")

    critic_rounds = meta.get('critic_rounds', 1)
    quality       = meta.get('critic_quality_score', '---')
    out.append(
        f"\\vspace{{8pt}}{{\\color{{C-rule}}\\rule{{\\textwidth}}{{0.3pt}}}}\n"
        f"{{\\tiny\\textcolor{{C-light}}{{"
        f"Classification: {cls_str}\\quad\\textbullet\\quad "
        f"Critic rounds: {critic_rounds}\\quad\\textbullet\\quad "
        f"Quality: {quality}/100\\quad\\textbullet\\quad "
        f"Model: Claude Haiku 4.5\\quad\\textbullet\\quad "
        f"Platform: BALAGAER Intelligence}}}}\n"
        f"\n\\end{{document}}\n"
    )

    return ''.join(out)
