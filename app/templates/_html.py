"""
Shared HTML rendering utilities for report templates.
Matches Witness/Proof design language: Georgia serif, #F3F2ED, monospace data.
"""

import os

CANONICAL_BASE_URL = os.environ.get("CANONICAL_BASE_URL", "https://basisprotocol.xyz").rstrip("/")

CSS = """
:root {
    --paper: #f5f2ec; --paper-warm: #f0ece3;
    --ink: #0a0a0a; --ink-mid: #3a3a3a; --ink-light: #6a6a6a; --ink-faint: #9a9a9a;
    --rule-mid: #c8c4bc; --rule-light: #e0ddd6;
    --accent: #c0392b;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { background: var(--paper); }
body { font-family: var(--sans); background: var(--paper); color: var(--ink); -webkit-font-smoothing: antialiased; margin: 0; padding: 0; line-height: 1.6; }
h1 { font-family: var(--sans); font-size: 1.6rem; font-weight: 400; letter-spacing: -0.3px; margin-bottom: 4px; }
h3 { font-family: var(--mono); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1.5px; color: var(--ink-light); margin: 0 0 12px; }
.meta { font-family: var(--mono); font-size: 0.75rem; color: var(--ink-faint); margin-bottom: 6px; }
.page-wrap { max-width: 1100px; margin: 0 auto; padding: 32px 24px 0; }
.page-frame { border: 3px solid var(--ink); box-shadow: 6px 6px 0 0 var(--rule-mid); background: var(--paper); }
.nav-bar { padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
.nav-tabs { display: flex; gap: 16px; }
.nav-tabs a { padding: 4px 0; border: none; font-size: 12px; font-weight: 400; font-family: var(--sans); color: var(--ink-light); text-decoration: none; border-bottom: 2px solid transparent; transition: color 0.15s; }
.nav-tabs a:hover { color: var(--ink); }
.nav-tabs a.active { font-weight: 600; color: var(--ink); border-bottom: 2px solid var(--ink); }
.nav-rule { border-top: 1px solid var(--rule-light); }
.page-content { padding: 0 24px 24px; }
.page-footer { padding: 10px 24px; border-top: 1px solid var(--rule-light); display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10px; color: var(--ink-faint); }
.page-footer a { color: inherit; text-decoration: none; border-bottom: 1px solid var(--rule-mid); }
.section { border: 1px solid #ccc; padding: 16px 20px; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th { text-align: left; padding: 6px 8px; border-bottom: 2px solid var(--ink); font-family: var(--mono); font-size: 0.65rem; text-transform: uppercase; letter-spacing: 1px; color: var(--ink-light); }
td { padding: 6px 8px; border-bottom: 1px dotted #ccc; }
.num { font-family: var(--mono); text-align: right; }
.score { font-family: var(--mono); font-size: 1.8rem; font-weight: 700; }
code { font-family: var(--mono); font-size: 0.8rem; background: #e8e6e0; padding: 1px 4px; border-radius: 2px; }
footer { margin-top: 32px; font-family: var(--mono); font-size: 0.75rem; color: var(--ink-faint); border-top: 1px solid #ccc; padding-top: 12px; }
.pass { color: #2d6b45; } .fail { color: #c0392b; }
.src-live { color: #2d6b45; } .src-cda { color: #6b5b2d; } .src-static { color: #9a9a9a; }
.bar { display: inline-block; height: 8px; background: var(--ink); border-radius: 1px; }
.pill { font-family: var(--mono); font-size: 0.65rem; padding: 2px 6px; border-radius: 2px; display: inline-block; }
.pill-pass { background: rgba(45,107,69,0.1); color: #2d6b45; }
.pill-fail { background: rgba(192,57,43,0.1); color: #c0392b; }
a { color: inherit; text-decoration: none; }
a:hover { border-bottom: 1px solid var(--rule-mid); }
.tab-header { border: 1.5px solid var(--ink); margin-top: 20px; margin-bottom: 24px; }
.tab-header-top { padding: 18px 24px 0; display: flex; justify-content: space-between; align-items: center; }
.tab-header-title { font-family: var(--sans); font-size: 28px; font-weight: 400; color: var(--ink); letter-spacing: -0.3px; }
.tab-header-form-id { font-family: var(--mono); font-size: 10px; color: var(--ink-faint); text-transform: uppercase; letter-spacing: 2px; }
.tab-header-rule { height: 1px; background: var(--rule-mid); margin: 12px 24px; }
.tab-header-stats { display: flex; align-items: center; padding: 0 24px 14px; flex-wrap: wrap; }
.tab-header-stats span { font-family: var(--mono); font-size: 10px; color: var(--ink-light); text-transform: uppercase; letter-spacing: 1.5px; padding: 0 12px; }
.tab-header-divider { width: 1px; height: 12px; background: var(--rule-mid); flex-shrink: 0; }
@media (max-width: 600px) {
    .page-wrap { padding: 8px 6px 0; }
    .page-frame { border-width: 2px; box-shadow: none; }
    .page-content { padding: 0 12px 16px; }
    .score { font-size: 1.4rem; }
    .tab-header-top { flex-direction: column; align-items: flex-start; gap: 4px; padding: 14px 12px 0; }
    .tab-header-title { font-size: 20px; }
    .tab-header-stats span { font-size: 8px; padding: 2px 6px; }
    .tab-header-divider { display: none; }
}
"""


def page(title: str, body: str, description: str = "", canonical: str = "",
         report_hash: str = "", timestamp: str = "",
         form_id: str = "", stats: list = None) -> str:
    """Wrap body content in a full HTML page with explorer frame."""
    tab_header_html = ""
    if form_id:
        stat_items = ""
        if stats:
            for i, s in enumerate(stats):
                stat_items += f'<span>{s}</span>'
                if i < len(stats) - 1:
                    stat_items += '<div class="tab-header-divider"></div>'
        tab_header_html = f'''<div class="tab-header">
  <div class="tab-header-top">
    <div class="tab-header-title">{title}</div>
    <div class="tab-header-form-id">{form_id}</div>
  </div>
  <div class="tab-header-rule"></div>
  {f'<div class="tab-header-stats">{stat_items}</div>' if stat_items else ''}
</div>'''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Basis Protocol</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title} — Basis Protocol">
{f'<link rel="canonical" href="{canonical}">' if canonical else ''}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="page-wrap">
  <div class="page-frame">
    <div class="nav-bar">
      <nav class="nav-tabs">
        <a href="/">Stablecoins</a>
        <a href="/#protocols">Protocols</a>
        <a href="/#wallets">Wallets</a>
        <a href="/#witness">Witness</a>
        <a href="/developers">API</a>
      </nav>
    </div>
    <div class="nav-rule"></div>
    <div class="page-content">
      {tab_header_html}
      {body}
    </div>
    <div class="page-footer">
      <span>Basis Protocol &middot; Stablecoin Integrity Index</span>
      <span><a href="/developers">API &amp; Pricing</a> &middot; <a href="/terms">Terms</a> &middot; basisprotocol.xyz</span>
    </div>
  </div>
  <div style="height: 32px;"></div>
</div>
</body>
</html>"""


def section(title: str, content: str) -> str:
    return f'<div class="section"><h3>{title}</h3>{content}</div>'


def score_header(name: str, score, grade: str = "", subtitle: str = "") -> str:
    """Render score header. Grade parameter kept for backward compatibility but no longer displayed."""
    s = f"{float(score):.1f}" if score is not None else "—"
    return f"""<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px">
<div><span style="font-size:1.4rem;font-weight:600">{name}</span>
{f'<br><span class="meta">{subtitle}</span>' if subtitle else ''}</div>
<div><span class="score">{s}</span></div>
</div>"""


def attestation_footer(report_hash: str, methodology_version: str,
                       timestamp: str, lens: str = None, lens_version: str = None) -> str:
    parts = [
        f"Report hash: <code>{report_hash}</code>",
        f'Verify: <a href="/api/reports/verify/{report_hash}">{CANONICAL_BASE_URL}/api/reports/verify/{report_hash}</a>',
        f"Generated: {timestamp}",
        f"Methodology: {methodology_version}",
    ]
    if lens:
        parts.append(f"Lens: {lens} v{lens_version or '1.0'}")
    return "<footer>" + "<br>".join(parts) + "<br>Basis Protocol</footer>"


def table(headers: list[str], rows: list[list[str]], num_cols: list[int] = None) -> str:
    """Render an HTML table."""
    num_cols = num_cols or []
    h = "<table><thead><tr>"
    for i, header in enumerate(headers):
        cls = ' class="num"' if i in num_cols else ""
        h += f"<th{cls}>{header}</th>"
    h += "</tr></thead><tbody>"
    for row in rows:
        h += "<tr>"
        for i, cell in enumerate(row):
            cls = ' class="num"' if i in num_cols else ""
            h += f"<td{cls}>{cell}</td>"
        h += "</tr>"
    h += "</tbody></table>"
    return h


def proof_link(url: str, label: str = "Proof") -> str:
    if not url:
        return "—"
    return f'<a href="{url}" style="color:#6a6a6a;font-size:0.75rem">{label}</a>'


def grade_color(grade: str) -> str:
    """Deprecated: grade display has been removed for legal reasons. Kept for backward compatibility."""
    if not grade:
        return "#6a6a6a"
    g = grade[0]
    if g == "A":
        return "#2d6b45"
    if g == "B":
        return "#3a6b2d"
    if g == "C":
        return "#6b5b2d"
    if g == "D":
        return "#6b3a2d"
    return "#c0392b"


def fmt_usd(val) -> str:
    if val is None:
        return "—"
    v = float(val)
    if v >= 1e9:
        return f"${v/1e9:.1f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:,.0f}"
