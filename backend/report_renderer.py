"""
Generates a PDF from a report dict using ReportLab (no LaTeX required).

Also exposes render_latex() for legacy use or manual compilation.
"""

import io
import math
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
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

# ── Dark-mode colour palette ───────────────────────────────────────────────────

C_BG_PAGE   = colors.Color( 11/255,  17/255,  24/255)  # #0B1118  deep navy
C_BG_PANEL  = colors.Color( 18/255,  26/255,  35/255)  # #121A23  panel
C_BG_PANEL2 = colors.Color( 14/255,  21/255,  29/255)  # slightly darker panel
C_TEAL      = colors.Color(  0/255, 209/255, 193/255)  # #00D1C1  brand accent
C_YELLOW    = colors.Color(244/255, 180/255,   0/255)  # #F4B400  medium risk
C_RED_RISK  = colors.Color(255/255,  77/255,  79/255)  # #FF4D4F  high risk
C_GRAY_META = colors.Color(138/255, 151/255, 166/255)  # #8A97A6  metadata
C_TEXT      = colors.Color(220/255, 228/255, 237/255)  # #DCE4ED  main text
C_RULE      = colors.Color( 30/255,  42/255,  54/255)  # subtle dark divider

TIER_COLOR = {
    "HIGH":    C_RED_RISK,
    "MEDIUM":  C_YELLOW,
    "LOW":     C_TEAL,
    "UNKNOWN": C_GRAY_META,
}

PAGE_W, PAGE_H = A4
MARGIN    = 2.0 * cm
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H  = 1.85 * cm
FOOTER_H  = 1.5  * cm


# ── Logo drawing ───────────────────────────────────────────────────────────────

def _draw_pelagos_logo(c, x: float, y: float, height: float = 0.55 * cm) -> None:
    """
    Draw a simplified Pelagos logo directly on the canvas.
    (x, y) = bottom-left corner.  height = total height of the logo.
    """
    r  = height / 2
    cx = x + r
    cy = y + r

    # Teal filled sphere
    c.setFillColor(C_TEAL)
    c.circle(cx, cy, r, fill=1, stroke=0)

    # White swoosh lines inside the sphere
    c.setStrokeColor(colors.white)
    c.setLineWidth(max(0.5, r * 0.18))
    c.setLineCap(1)  # round caps

    # Upper swoosh
    p = c.beginPath()
    p.moveTo(cx - r * 0.62, cy + r * 0.20)
    p.curveTo(
        cx - r * 0.18, cy + r * 0.55,
        cx + r * 0.18, cy + r * 0.02,
        cx + r * 0.62, cy + r * 0.28,
    )
    c.drawPath(p, stroke=1, fill=0)

    # Lower swoosh
    p = c.beginPath()
    p.moveTo(cx - r * 0.62, cy - r * 0.25)
    p.curveTo(
        cx - r * 0.18, cy + r * 0.12,
        cx + r * 0.18, cy - r * 0.42,
        cx + r * 0.62, cy - r * 0.15,
    )
    c.drawPath(p, stroke=1, fill=0)

    # "PELAGOS" wordmark
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", height * 0.70)
    c.drawString(cx + r + height * 0.25, cy - height * 0.25, "PELAGOS")


# ── Globe watermark ────────────────────────────────────────────────────────────

def _draw_watermark(c, w: float, h: float) -> None:
    """Concentric circles + crosshairs at 5 % teal opacity."""
    cx = w * 0.74
    cy = h * 0.42
    wm = colors.Color(0 / 255, 209 / 255, 193 / 255, 0.05)
    c.setStrokeColor(wm)
    c.setLineWidth(0.4)
    for r in [h * 0.07, h * 0.13, h * 0.20, h * 0.28, h * 0.36]:
        c.circle(cx, cy, r, fill=0, stroke=1)
    c.setLineWidth(0.25)
    c.line(cx - h * 0.36, cy, cx + h * 0.36, cy)
    c.line(cx, cy - h * 0.36, cx, cy + h * 0.36)


# ── Page template (header + footer drawn on canvas) ────────────────────────────

class _DarkPageTemplate:
    def __init__(self, now_str: str) -> None:
        self.now_str = now_str

    def __call__(self, canvas, doc) -> None:
        w, h = A4
        canvas.saveState()

        # Full-page dark background
        canvas.setFillColor(C_BG_PAGE)
        canvas.rect(0, 0, w, h, fill=1, stroke=0)

        # Subtle watermark (drawn first, behind everything)
        _draw_watermark(canvas, w, h)

        # Header panel
        canvas.setFillColor(C_BG_PANEL)
        canvas.rect(0, h - HEADER_H, w, HEADER_H, fill=1, stroke=0)

        # Pelagos logo
        logo_h = 0.56 * cm
        logo_y = h - HEADER_H + (HEADER_H - logo_h) / 2
        _draw_pelagos_logo(canvas, MARGIN, logo_y, height=logo_h)

        # Header metadata (right-aligned)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(C_GRAY_META)
        meta_cy = h - HEADER_H / 2
        canvas.drawRightString(
            w - MARGIN, meta_cy + 3,
            f"Generated: {self.now_str}  |  Classification: RESTRICTED",
        )
        canvas.drawRightString(
            w - MARGIN, meta_cy - 8,
            "Platform: PELAGOS Intelligence",
        )

        # Teal divider below header
        canvas.setStrokeColor(C_TEAL)
        canvas.setLineWidth(0.8)
        canvas.line(0, h - HEADER_H, w, h - HEADER_H)

        # Footer teal divider
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, FOOTER_H, w - MARGIN, FOOTER_H)

        # Footer text
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(C_GRAY_META)
        fy = FOOTER_H - 0.55 * cm
        canvas.drawString(MARGIN, fy, "PELAGOS Intelligence")
        canvas.drawCentredString(
            w / 2, fy,
            "Confidential \u2014 For Insurance & Compliance Use Only",
        )
        canvas.drawRightString(w - MARGIN, fy, f"Page {doc.page} of 2")

        canvas.restoreState()


# ── Risk Dial Flowable ─────────────────────────────────────────────────────────

class RiskDial(Flowable):
    """Circular gauge showing ML risk probability."""

    def __init__(
        self,
        percentage: int,
        tier: str,
        confidence,
        status: str,
        tier_color,
        size: float = 4.2 * cm,
    ) -> None:
        Flowable.__init__(self)
        self.percentage  = percentage
        self.tier        = tier
        self.confidence  = confidence
        self.status      = status
        self.tier_color  = tier_color
        self.size        = size
        self.width       = size
        self.height      = size + 0.9 * cm

    def draw(self) -> None:
        c   = self.canv
        cx  = self.size / 2
        cy  = self.size / 2 + 0.6 * cm
        r   = self.size * 0.41

        # Panel background
        c.setFillColor(C_BG_PANEL)
        c.circle(cx, cy, r + 8, fill=1, stroke=0)

        # Full track arc (dark, 270° from 225° clockwise)
        c.setStrokeColor(colors.Color(0.14, 0.20, 0.27))
        c.setLineWidth(10)
        c.setLineCap(1)
        c.arc(cx - r, cy - r, cx + r, cy + r, startAng=225, extent=-270)

        # Colored progress arc
        if self.percentage > 0:
            ext = -(self.percentage / 100.0) * 270
            c.setStrokeColor(self.tier_color)
            c.setLineWidth(10)
            c.arc(cx - r, cy - r, cx + r, cy + r, startAng=225, extent=ext)

            # End-point dot
            end_rad = math.radians(225 - (self.percentage / 100.0) * 270)
            ex = cx + r * math.cos(end_rad)
            ey = cy + r * math.sin(end_rad)
            c.setFillColor(self.tier_color)
            c.circle(ex, ey, 5.5, fill=1, stroke=0)

        # Center: percentage
        pct_fs = r * 0.62
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", pct_fs)
        c.drawCentredString(cx, cy - pct_fs * 0.28, f"{self.percentage}%")

        # Center: tier badge
        c.setFillColor(self.tier_color)
        c.setFont("Helvetica-Bold", r * 0.27)
        c.drawCentredString(cx, cy - pct_fs * 0.28 - r * 0.38, self.tier)

        # Labels below dial
        c.setFillColor(C_GRAY_META)
        c.setFont("Courier", 7)
        conf_str = (
            f"Confidence: {self.confidence}%"
            if self.confidence is not None else "Confidence: \u2014"
        )
        c.drawCentredString(cx, 0.42 * cm, conf_str)
        c.drawCentredString(cx, 0.18 * cm, f"Status: {self.status}")


# ── Colored left-bar item ──────────────────────────────────────────────────────

class _ColorBarItem(Flowable):
    """Paragraph with a colored left accent bar."""

    def __init__(
        self,
        text: str,
        style: ParagraphStyle,
        accent_color,
        bar_w: float = 3,
        gap: float = 8,
    ) -> None:
        Flowable.__init__(self)
        self.text         = text
        self.style        = style
        self.accent_color = accent_color
        self.bar_w        = bar_w
        self.gap          = gap
        self._para        = None
        self.spaceAfter   = getattr(style, "spaceAfter",  4)
        self.spaceBefore  = getattr(style, "spaceBefore", 0)

    def wrap(self, avail_w: float, avail_h: float):
        self._para = Paragraph(self.text, self.style)
        _, h = self._para.wrap(avail_w - self.bar_w - self.gap, avail_h)
        self.width  = avail_w
        self.height = h + 8
        return self.width, self.height

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(self.accent_color)
        c.rect(0, 2, self.bar_w, self.height - 4, fill=1, stroke=0)
        self._para.drawOn(c, self.bar_w + self.gap, 4)


# ── Styles ─────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    def S(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "classification": S("classification",
            fontName="Helvetica-Bold", fontSize=7,
            textColor=C_RED_RISK, alignment=TA_CENTER, spaceAfter=4),
        "title": S("title",
            fontName="Helvetica-Bold", fontSize=20,
            textColor=colors.white, alignment=TA_LEFT,
            leading=24, spaceAfter=5),
        "vessel": S("vessel",
            fontName="Courier-Bold", fontSize=10,
            textColor=C_TEAL, alignment=TA_LEFT, spaceAfter=6),
        "section": S("section",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=C_GRAY_META, spaceBefore=12, spaceAfter=4, leading=10),
        "body": S("body",
            fontName="Helvetica", fontSize=9,
            textColor=C_TEXT, leading=15, spaceAfter=4),
        "body_lead": S("body_lead",
            fontName="Helvetica-Bold", fontSize=10,
            textColor=C_TEXT, leading=16, spaceAfter=5),
        "body_italic": S("body_italic",
            fontName="Helvetica-Oblique", fontSize=8.5,
            textColor=C_GRAY_META, leading=14, spaceAfter=4),
        "small": S("small",
            fontName="Helvetica", fontSize=7.5,
            textColor=C_GRAY_META, leading=11),
        "small_mono": S("small_mono",
            fontName="Courier", fontSize=7.5,
            textColor=C_TEXT, leading=11),
        "label": S("label",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=C_GRAY_META, leading=10, spaceAfter=1),
        "card_title": S("card_title",
            fontName="Helvetica-Bold", fontSize=7.5,
            textColor=C_TEAL, spaceAfter=3, leading=10),
        "card_body": S("card_body",
            fontName="Helvetica", fontSize=7.5,
            textColor=C_GRAY_META, leading=12, spaceAfter=0),
        "ev_header": S("ev_header",
            fontName="Helvetica-Bold", fontSize=8.5,
            textColor=C_TEXT, spaceAfter=5, leading=12),
        "bullet": S("bullet",
            fontName="Helvetica", fontSize=8.5,
            textColor=C_TEXT, leading=14, leftIndent=10, spaceAfter=3),
        "action": S("action",
            fontName="Helvetica", fontSize=8.5,
            textColor=C_TEXT, leading=14, spaceAfter=0),
        "analyst_label": S("analyst_label",
            fontName="Helvetica-Bold", fontSize=7,
            textColor=C_TEAL, spaceAfter=5, leading=10),
        "footer": S("footer",
            fontName="Helvetica", fontSize=6.5,
            textColor=C_GRAY_META, alignment=TA_CENTER),
        "threat": S("threat",
            fontName="Helvetica", fontSize=9,
            textColor=C_GRAY_META, leading=14, spaceAfter=4),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hex(c) -> str:
    return "#{:02X}{:02X}{:02X}".format(
        int(c.red * 255), int(c.green * 255), int(c.blue * 255)
    )


def _tag(text: str, color) -> str:
    return f'<font color="{_hex(color)}"><b>{text}</b></font>'


def _section(title: str, styles: dict) -> list:
    return [
        _ColorBarItem(title.upper(), styles["section"], C_TEAL, bar_w=2, gap=6),
        HRFlowable(width="100%", thickness=0.4, color=C_RULE, spaceAfter=6),
    ]


def _bullet_list(items: list, styles: dict) -> list:
    out = []
    dot = f'<font color="{_hex(C_GRAY_META)}">·</font>'
    for item in items:
        out.append(Paragraph(f"{dot}  {item}", styles["bullet"]))
    return out


def _action_tier(text: str, idx: int, ml_tier: str) -> tuple:
    tl = text.lower()
    urgent_kw = {"immediate", "urgent", "critical", "halt", "stop", "alert", "seize"}
    high_kw   = {"investigate", "notify", "report", "escalate", "verify", "flag", "review"}
    if any(k in tl for k in urgent_kw) or (ml_tier == "HIGH" and idx == 0):
        return "URGENT", C_RED_RISK
    if any(k in tl for k in high_kw) or idx < 3:
        return "HIGH", C_YELLOW
    return "MEDIUM", C_TEAL


def _dark_tbl(extra: list | None = None) -> TableStyle:
    cmds = [
        ("BACKGROUND", (0, 0), (-1, -1), C_BG_PANEL),
        ("BOX",        (0, 0), (-1, -1), 0.5, C_TEAL),
        ("INNERGRID",  (0, 0), (-1, -1), 0.3, C_RULE),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
    ]
    if extra:
        cmds.extend(extra)
    return TableStyle(cmds)


# ── Main PDF renderer ──────────────────────────────────────────────────────────

def render_pdf(report: dict) -> bytes:
    """Return a PDF as bytes from a report dict."""

    meta     = report.get("_meta", {})
    is_inv   = "ml_risk_score" in report
    ml       = report.get("ml_risk_score") or {}
    now_str  = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    styles   = _build_styles()

    title    = report.get("title", "Maritime Intelligence Assessment")
    cls_str  = report.get("classification", "INTELLIGENCE REPORT - RESTRICTED")
    exec_sum = report.get("executive_summary", "")
    threat   = report.get("threat_assessment", "")
    cot      = report.get("chain_of_thought", "")

    evidence    = report.get("supporting_evidence", []) or []
    risks       = report.get("risk_factors",        []) or []
    actions     = report.get("recommended_actions", []) or []
    predictions = report.get("commodity_predictions",[]) or []

    ml_pct     = int((ml.get("probability", 0)) * 100)
    tier       = ml.get("risk_tier", "UNKNOWN")
    conf       = report.get("overall_confidence")
    approved   = meta.get("final_approved", False)
    tier_clr   = TIER_COLOR.get(tier, C_GRAY_META)

    conf_str   = f"{conf}%" if conf is not None else "\u2014"
    status_str = "APPROVED" if approved else "PROVISIONAL"
    status_clr = C_TEAL if approved else C_YELLOW

    # ── Document setup ─────────────────────────────────────────────────────────
    buf        = io.BytesIO()
    page_tmpl  = _DarkPageTemplate(now_str)

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=HEADER_H + 0.5 * cm,
        bottomMargin=FOOTER_H + 0.5 * cm,
        title=title,
        author="PELAGOS Intelligence Platform",
    )
    frame = Frame(
        MARGIN,
        FOOTER_H + 0.4 * cm,
        CONTENT_W,
        PAGE_H - HEADER_H - FOOTER_H - 0.95 * cm,
        id="main",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=page_tmpl)
    ])

    story = []

    # ── Title block ────────────────────────────────────────────────────────────
    if is_inv:
        mmsi_val   = str(meta.get("mmsi", ml.get("mmsi", "\u2014")))
        title_col  = [
            Spacer(1, 0.2 * cm),
            Paragraph(cls_str.upper(), styles["classification"]),
            Paragraph("DARK FLEET RISK ASSESSMENT", styles["title"]),
            Paragraph(f"UNIDENTIFIED VESSEL \u2014 MMSI {mmsi_val}", styles["vessel"]),
        ]
        dial = RiskDial(ml_pct, tier, conf, status_str, tier_clr, size=4.2 * cm)
        ttbl = Table(
            [[title_col, dial]],
            colWidths=[CONTENT_W - 4.8 * cm, 4.8 * cm],
            hAlign="LEFT",
        )
        ttbl.setStyle(TableStyle([
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ]))
        story.append(ttbl)
    else:
        story.append(Paragraph(cls_str.upper(), styles["classification"]))
        story.append(Paragraph(title, styles["title"]))

    story.append(HRFlowable(width="100%", thickness=0.6, color=C_TEAL, spaceAfter=8))

    # ── Meta bar ───────────────────────────────────────────────────────────────
    col_w = CONTENT_W / 4

    if is_inv:
        mmsi_val = str(meta.get("mmsi", ml.get("mmsi", "\u2014")))
        headers  = ["MMSI", "ML RISK SCORE", "CONFIDENCE", "STATUS"]
        val_strs = [mmsi_val, f"{ml_pct}%  {tier}", conf_str, status_str]
        val_clrs = [None, tier_clr, None, status_clr]
    else:
        region_val = str(meta.get("region", "\u2014"))
        inc_count  = str(int(meta.get("incident_count", 0)))
        headers    = ["REGION", "INCIDENTS", "CONFIDENCE", "STATUS"]
        val_strs   = [region_val, inc_count, conf_str, status_str]
        val_clrs   = [None, None, None, status_clr]

    h_row = [Paragraph(h, styles["label"]) for h in headers]
    v_row = []
    for i, (v, vc) in enumerate(zip(val_strs, val_clrs)):
        if vc:
            v_row.append(Paragraph(_tag(v, vc), styles["small"]))
        elif i in (0, 2):
            v_row.append(Paragraph(v, styles["small_mono"]))
        else:
            v_row.append(Paragraph(v, styles["small"]))

    meta_tbl = Table([h_row, v_row], colWidths=[col_w] * 4, hAlign="LEFT")
    meta_tbl.setStyle(_dark_tbl([
        ("BACKGROUND", (0, 0), (-1, 0), C_BG_PANEL2),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 10))

    # ── Assessment ─────────────────────────────────────────────────────────────
    story.extend(_section("Assessment", styles))

    if exec_sum:
        # Lead sentence in bold, rest normal — both with teal left accent
        dot_idx = exec_sum.find(". ")
        if 0 < dot_idx < 200:
            lead = exec_sum[: dot_idx + 1]
            rest = exec_sum[dot_idx + 2 :]
            story.append(_ColorBarItem(lead, styles["body_lead"], C_TEAL, bar_w=2, gap=8))
            if rest:
                story.append(_ColorBarItem(rest, styles["body"], C_TEAL, bar_w=2, gap=8))
        else:
            story.append(_ColorBarItem(exec_sum, styles["body_lead"], C_TEAL, bar_w=2, gap=8))

    if threat and threat != exec_sum:
        story.append(Paragraph(threat, styles["threat"]))

    # ── ML Score (investigation only) ─────────────────────────────────────────
    if is_inv:
        interp = ml.get("interpretation", "")
        if interp:
            story.append(Paragraph(
                f'{_tag("ML Score:", C_GRAY_META)} {_tag(f"{ml_pct}% {tier}", tier_clr)}'
                f' \u2014 <i>{interp}</i>',
                styles["body"],
            ))

    # ── Intelligence source cards (investigation only) ─────────────────────────
    if is_inv:
        news_txt = report.get("news_intelligence",   "") or ""
        sanc_txt = report.get("sanctions_assessment","") or ""
        geo_txt  = report.get("geopolitical_context","") or ""

        if news_txt or sanc_txt or geo_txt:
            story.extend(_section("Intelligence Sources", styles))

            def _card(label: str, accent, text: str, limit: int = 360) -> list:
                t = (text[:limit] + "\u2026") if len(text) > limit else text
                return [
                    Paragraph(label, ParagraphStyle(
                        "ct", fontName="Helvetica-Bold", fontSize=7.5,
                        textColor=accent, spaceAfter=3, leading=10,
                    )),
                    HRFlowable(width="100%", thickness=0.4, color=C_RULE, spaceAfter=5),
                    Paragraph(t, styles["card_body"]),
                ]

            col3    = CONTENT_W / 3
            src_tbl = Table(
                [[_card("NEWS", C_TEAL, news_txt),
                  _card("SANCTIONS", C_YELLOW, sanc_txt),
                  _card("GEOPOLITICAL", C_RED_RISK, geo_txt)]],
                colWidths=[col3, col3, col3],
                hAlign="LEFT",
            )
            src_tbl.setStyle(_dark_tbl())
            story.append(src_tbl)

    # ── Evidence + Risk Factors ────────────────────────────────────────────────
    if evidence or risks:
        story.extend(_section("Evidence and Risk Factors", styles))

        if evidence and risks:
            ev_col = ([Paragraph("Supporting Evidence", styles["ev_header"])]
                      + _bullet_list(evidence, styles))
            ri_col = ([Paragraph("Risk Factors", styles["ev_header"])]
                      + _bullet_list(risks, styles))
            half   = CONTENT_W / 2 - 4
            er_tbl = Table([[ev_col, ri_col]], colWidths=[half, half], hAlign="LEFT")
            er_tbl.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
                ("TOPPADDING",    (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            story.append(er_tbl)
        elif evidence:
            story.append(Paragraph("Supporting Evidence", styles["ev_header"]))
            story.extend(_bullet_list(evidence, styles))
        else:
            story.append(Paragraph("Risk Factors", styles["ev_header"]))
            story.extend(_bullet_list(risks, styles))

    # ── Recommended Actions (investigation only) ───────────────────────────────
    if is_inv and actions:
        story.extend(_section("Recommended Actions", styles))
        for i, action_text in enumerate(actions):
            _, accent = _action_tier(action_text, i, tier)
            story.append(_ColorBarItem(
                f"<b>{i + 1}.</b>  {action_text}",
                styles["action"],
                accent,
                bar_w=3,
                gap=8,
            ))
            story.append(Spacer(1, 3))
            if i < len(actions) - 1:
                story.append(HRFlowable(
                    width="100%", thickness=0.3, color=C_RULE, spaceAfter=3,
                ))

    # ── Commodity Predictions ──────────────────────────────────────────────────
    if predictions:
        story.extend(_section("Commodity Market Impact Forecast", styles))
        header_row = [
            Paragraph(h, styles["label"])
            for h in ["Commodity", "Current", "Forecast", "Timeframe", "Conf."]
        ]
        rows = [header_row]
        for p in predictions:
            hi   = p.get("predicted_change_pct_high", 0) or 0
            lo   = p.get("predicted_change_pct_low", hi) or hi
            sign = "+" if hi > 0 else ""
            pct  = f"{sign}{lo}%\u2013{sign}{hi}%" if lo != hi else f"{sign}{hi}%"
            clr  = C_RED_RISK if hi > 0 else C_TEAL
            rows.append([
                Paragraph(str(p.get("commodity",     "")), styles["small"]),
                Paragraph(str(p.get("current_price", "")), styles["small_mono"]),
                Paragraph(_tag(pct, clr),                  styles["small_mono"]),
                Paragraph(str(p.get("timeframe",     "")), styles["small"]),
                Paragraph(f"{p.get('confidence', 0)}%",    styles["small_mono"]),
            ])
        cw = CONTENT_W
        pred_tbl = Table(
            rows,
            colWidths=[cw*0.28, cw*0.14, cw*0.18, cw*0.24, cw*0.16],
            hAlign="LEFT",
            repeatRows=1,
        )
        pred_tbl.setStyle(_dark_tbl([
            ("BACKGROUND",    (0, 0), (-1,  0), C_BG_PANEL2),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [C_BG_PANEL, C_BG_PANEL2]),
        ]))
        story.append(pred_tbl)

    # ── Analyst Reasoning ──────────────────────────────────────────────────────
    if cot:
        story.extend(_section("Analyst Reasoning", styles))
        analyst_content = [
            Paragraph("ANALYST COMMENTARY", styles["analyst_label"]),
            Paragraph(cot, styles["body_italic"]),
        ]
        analyst_tbl = Table([[analyst_content]], colWidths=[CONTENT_W], hAlign="LEFT")
        analyst_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), C_BG_PANEL2),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 12),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 12),
            ("LINEBEFORE",    (0, 0), ( 0, -1),  2, C_TEAL),
        ]))
        story.append(analyst_tbl)

    # ── End matter ─────────────────────────────────────────────────────────────
    critic_rounds = meta.get("critic_rounds", 1)
    quality       = meta.get("critic_quality_score", "\u2014")
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.4, color=C_RULE, spaceAfter=4))
    story.append(Paragraph(
        f"Classification: {cls_str}  \u00b7  Critic rounds: {critic_rounds}  \u00b7  "
        f"Quality: {quality}/100  \u00b7  Model: Claude Haiku 4.5  \u00b7  "
        f"Platform: PELAGOS Intelligence",
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
