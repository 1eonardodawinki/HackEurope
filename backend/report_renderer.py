"""
Generates a LaTeX source document from a report dict.

Compile with:
    pdflatex -interaction=nonstopmode report.tex

Requires standard packages available in any TeX Live / MiKTeX installation:
    geometry, helvet, xcolor, titlesec, enumitem, fancyhdr,
    microtype, parskip, booktabs, tabularx
"""

from datetime import datetime, timezone


# ── Character escaping ────────────────────────────────────────────────────────

def _esc(s) -> str:
    """Escape LaTeX special characters in a string."""
    if s is None:
        return ''
    s = str(s)
    s = s.replace('\\', 'XXBSXX')      # must be first — placeholder avoids double-escaping
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


def _itemize(items: list) -> str:
    if not items:
        return ''
    inner = '\n'.join(f'  \\item {_esc(x)}' for x in items)
    return f'\\begin{{itemize}}\n{inner}\n\\end{{itemize}}'


def _enumerate(items: list) -> str:
    if not items:
        return ''
    inner = '\n'.join(f'  \\item {_esc(x)}' for x in items)
    return f'\\begin{{enumerate}}\n{inner}\n\\end{{enumerate}}'


# ── Main renderer ─────────────────────────────────────────────────────────────

def render_latex(report: dict) -> str:
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

    out = []

    # ── Preamble ──────────────────────────────────────────────────────────────
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

%% Colour palette
\definecolor{C-mid}{RGB}{90,90,90}
\definecolor{C-light}{RGB}{160,160,160}
\definecolor{C-rule}{RGB}{210,210,210}
\definecolor{C-danger}{RGB}{155,20,20}
\definecolor{C-warn}{RGB}{150,85,0}
\definecolor{C-green}{RGB}{20,105,45}
\definecolor{C-accent}{RGB}{0,75,155}

\setlength{\parskip}{5pt}
\setlength{\parindent}{0pt}

%% Section headers: small-caps label + rule
\titleformat{\section}
  {\normalfont\scriptsize\bfseries\color{C-mid}\MakeUppercase}
  {}{0em}{}[\vspace{1pt}{\color{C-rule}\titlerule}]
\titlespacing{\section}{0pt}{16pt}{8pt}

%% Page header / footer
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\tiny\textcolor{C-light}{INTELLIGENCE REPORT --- RESTRICTED}}
\fancyhead[R]{\tiny\textcolor{C-light}{BALAGAER INTELLIGENCE PLATFORM}}
\fancyfoot[C]{\tiny\textcolor{C-light}{\thepage}}
\renewcommand{\headrulewidth}{0.3pt}
\renewcommand{\headrule}{\color{C-rule}\hrule width\headwidth height\headrulewidth}

%% List styles
\setlist[itemize]{leftmargin=12pt,itemsep=2pt,topsep=3pt,parsep=0pt,label=\textendash}
\setlist[enumerate]{leftmargin=16pt,itemsep=2pt,topsep=3pt,parsep=0pt}

\begin{document}
""")

    # ── Title block ───────────────────────────────────────────────────────────
    out.append(f"""{{\\centering
  {{\\tiny\\textcolor{{C-danger}}{{\\textbf{{{cls_str}}}}}}}\\\\[5pt]
  {{\\Large\\textbf{{{title}}}}}\\\\[4pt]
  {{\\scriptsize\\textcolor{{C-mid}}{{BALAGAER Intelligence Monitoring Platform\\quad\\textbullet\\quad Generated {now}}}}}\\par}}
\\vspace{{5pt}}{{\\color{{C-rule}}\\rule{{\\textwidth}}{{0.5pt}}}}\\vspace{{5pt}}
""")

    # ── Meta bar ──────────────────────────────────────────────────────────────
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

    # ── Assessment ────────────────────────────────────────────────────────────
    out.append("\\section{Assessment}\n")
    out.append(exec_sum + "\n\n")
    if threat and threat != exec_sum:
        out.append(f"\\textcolor{{C-mid}}{{{threat}}}\n\n")

    # ── ML score note (investigation only) ────────────────────────────────────
    if is_inv:
        interp = _esc(ml.get('interpretation', ''))
        if interp:
            out.append(
                f"\\noindent\\textcolor{{C-mid}}{{\\textbf{{ML Score:}}}}\\ "
                f"\\textcolor{{{tier_color}}}{{{ml_pct}\\% {tier}}}"
                f" --- {{\\small\\textit{{{interp}}}}}\n\n"
            )

    # ── Intel sources (investigation only) ────────────────────────────────────
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

    # ── Evidence + Risk factors ────────────────────────────────────────────────
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

    # ── Recommended Actions (investigation only) ──────────────────────────────
    if is_inv and actions:
        out.append("\\section{Recommended Actions}\n")
        out.append(_enumerate(actions) + "\n")

    # ── Commodity Predictions (standard only) ─────────────────────────────────
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

    # ── Analyst Reasoning ─────────────────────────────────────────────────────
    if cot:
        out.append("\\section{Analyst Reasoning}\n")
        out.append(f"\\begin{{small}}\n\\textit{{{cot}}}\n\\end{{small}}\n\n")

    # ── Footer line ───────────────────────────────────────────────────────────
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
