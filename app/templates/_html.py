"""
Shared HTML rendering utilities for report templates.
Matches Witness/Proof design language: Georgia serif, #F3F2ED, monospace data.
"""

import os

CANONICAL_BASE_URL = os.environ.get("CANONICAL_BASE_URL", "https://basisprotocol.xyz").rstrip("/")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
:root {
    --paper: #f5f2ec;
    --paper-warm: #f0ece3;
    --ink: #0a0a0a;
    --ink-mid: #3a3a3a;
    --ink-light: #6a6a6a;
    --ink-faint: #9a9a9a;
    --rule-mid: #c8c4bc;
    --rule-light: #e0ddd6;
    --accent: #c0392b;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'IBM Plex Sans', system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { background: var(--paper); }
body {
    font-family: var(--sans);
    background: var(--paper);
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    max-width: 1100px;
    margin: 0 auto;
    padding: 32px 24px;
    line-height: 1.6;
}
.page-frame {
    border: 3px solid var(--ink);
    box-shadow: 6px 6px 0 0 var(--rule-mid);
    background: var(--paper);
}
.page-nav {
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.page-nav a {
    font-family: var(--sans);
    font-size: 12px;
    color: var(--ink-light);
    text-decoration: none;
    margin-right: 16px;
}
.page-nav a:hover { color: var(--ink); }
.page-content { padding: 0 24px 24px; }
.tab-header {
    border: 1.5px solid var(--ink);
    margin-top: 20px;
    margin-bottom: 24px;
}
.tab-header-top {
    padding: 18px 24px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.tab-header-title {
    font-family: var(--sans);
    font-size: 28px;
    font-weight: 400;
    color: var(--ink);
    letter-spacing: -0.3px;
}
.tab-header-form-id {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--ink-faint);
    text-transform: uppercase;
    letter-spacing: 2px;
}
.tab-header-rule { height: 1px; background: var(--rule-mid); margin: 12px 24px; }
.tab-header-stats {
    display: flex;
    align-items: center;
    padding: 0 24px 14px;
    flex-wrap: wrap;
}
.tab-header-stats span {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--ink-light);
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 0 12px;
}
.tab-header-divider {
    width: 1px;
    height: 12px;
    background: var(--rule-mid);
    flex-shrink: 0;
}
.tab-header-chain {
    border-top: 1px solid var(--rule-mid);
    padding: 8px 24px;
    display: flex;
    gap: 10px;
}
.chain-pill {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--ink-mid);
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--paper-warm);
    padding: 4px 12px;
    border-radius: 999px;
}
.chain-dot {
    width: 6px; height: 6px; border-radius: 50%;
    display: inline-block;
}
h3 {
    font-family: var(--mono);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--ink-light);
    margin: 0 0 12px;
    font-weight: 500;
}
.meta {
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--ink-faint);
    margin-bottom: 6px;
}
.section {
    border: 1px solid var(--rule-mid);
    padding: 16px 20px;
    margin-bottom: 20px;
}
table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
th {
    text-align: left; padding: 8px 8px;
    border-bottom: 3px solid var(--ink);
    font-family: var(--mono);
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--ink-light);
    font-weight: 500;
}
td {
    padding: 8px 8px;
    border-bottom: 1px dotted var(--rule-light);
    font-family: var(--mono);
    font-size: 0.8rem;
    color: var(--ink-mid);
}
.num { font-family: var(--mono); text-align: right; }
.score { font-family: var(--mono); font-size: 1.8rem; font-weight: 700; }
.grade { font-size: 1.4rem; font-weight: 700; }
code { font-family: var(--mono); font-size: 0.8rem; background: var(--paper-warm); padding: 1px 4px; border-radius: 2px; }
footer {
    margin-top: 32px;
    font-family: var(--mono);
    font-size: 0.75rem;
    color: var(--ink-faint);
    border-top: 1px solid var(--rule-mid);
    padding-top: 12px;
}
footer a { color: var(--ink-faint); text-decoration: none; border-bottom: 1px solid var(--rule-mid); }
.pass { color: #2d6b45; } .fail { color: var(--accent); }
.src-live { color: #2d6b45; } .src-cda { color: #6b5b2d; } .src-static { color: #9a9a9a; }
.bar { display: inline-block; height: 8px; background: var(--ink); border-radius: 1px; }
.pill { font-family: var(--mono); font-size: 0.65rem; padding: 2px 6px; border-radius: 2px; display: inline-block; }
.pill-pass { background: rgba(45,107,69,0.1); color: #2d6b45; }
.pill-fail { background: rgba(192,57,43,0.1); color: var(--accent); }
@media (max-width: 600px) {
    body { padding: 8px 6px; }
    .page-frame { border-width: 2px; box-shadow: none; }
    .page-content { padding: 0 12px 16px; }
    .tab-header-top { flex-direction: column; align-items: flex-start; gap: 4px; padding: 14px 12px 0; }
    .tab-header-title { font-size: 20px; }
    .tab-header-stats span { font-size: 8px; padding: 2px 6px; }
    .tab-header-divider { display: none; }
    .score { font-size: 1.4rem; }
}
"""


def page(title: str, body: str, description: str = "", canonical: str = "",
         report_hash: str = "", timestamp: str = "",
         form_id: str = "", stats: list = None) -> str:
    """Wrap body content in a full HTML page matching explorer design."""

    # Build tab-header if form_id provided
    header_html = ""
    if form_id:
        stats_html = ""
        if stats:
            parts = []
            for i, s in enumerate(stats):
                parts.append(f'<span>{s}</span>')
                if i < len(stats) - 1:
                    parts.append('<div class="tab-header-divider"></div>')
            stats_html = f'<div class="tab-header-stats">{"".join(parts)}</div>'

        header_html = f"""
        <div class="tab-header">
          <div class="tab-header-top">
            <div class="tab-header-title">{title}</div>
            <div class="tab-header-form-id">{form_id}</div>
          </div>
          <div class="tab-header-rule"></div>
          {stats_html}
          <div class="tab-header-chain">
            <a href="https://basescan.org/address/0x1651d7b2E238a952167E51A1263FFe607584DB83" target="_blank" rel="noopener noreferrer" class="chain-pill">
              <span class="chain-dot" style="background: #378ADD;"></span> Base
            </a>
            <a href="https://arbiscan.io/address/0x1651d7b2E238a952167E51A1263FFe607584DB83" target="_blank" rel="noopener noreferrer" class="chain-pill">
              <span class="chain-dot" style="background: #28A0F0;"></span> Arbitrum
            </a>
          </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Basis Protocol</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title} — Basis Protocol">
{f'<link rel="canonical" href="{canonical}">' if canonical else ''}
<style>{CSS}</style>
</head>
<body>
<div class="page-frame">
  <div class="page-nav">
    <div>
      <a href="/">Stablecoins</a>
      <a href="/#protocols">Protocols</a>
      <a href="/#wallets">Wallets</a>
      <a href="/#witness">Witness</a>
      <a href="/developers">API</a>
    </div>
  </div>
  <div style="border-top: 1px solid var(--rule-light);"></div>
  <div class="page-content">
    {header_html}
    {body}
  </div>
  <div style="border-top: 1px solid var(--rule-light); padding: 10px 24px; display: flex; justify-content: space-between;">
    <span style="font-family: var(--mono); font-size: 10px; color: var(--ink-faint);">Basis Protocol</span>
    <span style="font-family: var(--mono); font-size: 10px; color: var(--ink-faint);">basisprotocol.xyz</span>
  </div>
</div>
</body>
</html>"""


def section(title: str, content: str) -> str:
    return f'<div class="section"><h3>{title}</h3>{content}</div>'


def score_header(name: str, score, grade: str, subtitle: str = "") -> str:
    s = f"{float(score):.1f}" if score is not None else "—"
    return f"""<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px">
<div><span style="font-size:1.4rem;font-weight:600">{name}</span>
{f'<br><span class="meta">{subtitle}</span>' if subtitle else ''}</div>
<div><span class="score">{s}</span> <span class="grade" style="margin-left:8px">{grade or "—"}</span></div>
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
