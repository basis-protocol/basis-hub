"""
Protocol Risk Report Template
===============================
PSI score + stablecoin exposure + CQI composition.
"""

from app.templates._html import (
    page, section, score_header, attestation_footer,
    table, proof_link, fmt_usd, CANONICAL_BASE_URL,
)


def render(report_data: dict, lens_result: dict = None,
           report_hash: str = "", timestamp: str = "", format: str = "html") -> str:
    """Render protocol risk report as HTML."""
    d = report_data
    name = d.get("name", d.get("entity_id", "Unknown"))
    score = d.get("score")

    body = f'<p class="meta">Protocol Risk Report · {name} · {timestamp}</p>'
    body += score_header(name, score, subtitle=f"PSI {d.get('formula_version', '')}")

    # Lens classification (if provided)
    if lens_result:
        body += _render_lens_section(lens_result)

    # Category breakdown
    cat_scores = d.get("category_scores") or {}
    if cat_scores:
        rows = []
        for cat_id, cat_score in sorted(cat_scores.items()):
            s = f"{float(cat_score):.1f}" if cat_score is not None else "—"
            bar_w = int(float(cat_score or 0) * 1.5)
            rows.append([cat_id.replace("_", " ").title(), s,
                         f'<span class="bar" style="width:{bar_w}px"></span>'])
        body += section("Category Breakdown", table(["Category", "Score", ""], rows, [1]))

    # Stablecoin exposure
    exposure = d.get("exposure") or []
    if exposure:
        rows = []
        for e in exposure:
            s = f"{float(e['sii_score']):.1f}" if e.get("sii_score") else "—"
            link = proof_link(f"/proof/sii/{e.get('stablecoin_id', '')}")
            amt = fmt_usd(e.get("exposure_usd"))
            rows.append([e.get("symbol", "?"), e.get("name", ""), amt, s, link])
        body += section("Stablecoin Exposure",
                        table(["Symbol", "Name", "Exposure", "SII", "Proof"],
                              rows, [2, 3]))

    # CQI composition
    cqi_pairs = d.get("cqi_pairs") or []
    if cqi_pairs:
        rows = []
        for p in cqi_pairs:
            cqi_s = f"{float(p['cqi_score']):.1f}" if p.get("cqi_score") else "—"
            sii_s = f"{float(p['sii_score']):.1f}" if p.get("sii_score") else "—"
            psi_s = f"{float(p['psi_score']):.1f}" if p.get("psi_score") else "—"
            link = proof_link(p.get("proof_url", ""))
            rows.append([p.get("asset", "?"), sii_s, psi_s, cqi_s, link])
        body += section("Collateral Quality Index (CQI)",
                        '<p class="meta">Geometric mean of SII and PSI scores per stablecoin held.</p>' +
                        table(["Asset", "SII", "PSI", "CQI", "Proof"], rows, [1, 2, 3]))

    # RPI (Revenue Protocol Index)
    rpi = d.get("rpi")
    if rpi and rpi.get("score") is not None:
        rpi_s = f"{float(rpi['score']):.1f}"
        traj = rpi.get("trajectory") or {}
        traj_parts = []
        for label, delta in sorted(traj.items()):
            sign = "+" if delta >= 0 else ""
            traj_parts.append(f"{label}: {sign}{delta:.1f}")
        traj_str = " · ".join(traj_parts) if traj_parts else "no prior data"
        body += section("Revenue Protocol Index (RPI)",
                        f'<p>RPI Score: <strong>{rpi_s}</strong> · Grade: {rpi.get("grade", "—")} · Trajectory: {traj_str}</p>')
    elif rpi is None:
        body += section("Revenue Protocol Index (RPI)",
                        '<p class="meta"><em>Not yet monitored. RPI scoring requires governance and revenue data.</em></p>')

    # Governance Activity
    gov = d.get("governance_activity") or {}
    if gov.get("proposals_count") or gov.get("recent_high_impact") or gov.get("edited_after_publication"):
        gov_html = f'<p>{gov.get("proposals_count", 0)} proposals in last 30 days.</p>'
        edits = gov.get("edited_after_publication") or []
        if edits:
            gov_html += f'<p style="color:#c0392b"><strong>{len(edits)} proposal(s) edited after publication:</strong></p><ul>'
            for ed in edits[:5]:
                gov_html += f'<li>{ed.get("title", ed.get("proposal_id", ""))}</li>'
            gov_html += '</ul>'
        events = gov.get("recent_high_impact") or []
        if events:
            ev_rows = [[e.get("type", ""), e.get("title", ""), e.get("outcome", "—"), e.get("timestamp", "")[:10] if e.get("timestamp") else ""] for e in events]
            gov_html += table(["Type", "Title", "Outcome", "Date"], ev_rows, [])
        body += section("Governance Activity", gov_html)
    else:
        body += section("Governance Activity",
                        '<p class="meta"><em>No governance events captured in the last 30 days.</em></p>')

    # Parameter Changes
    params = d.get("parameter_changes") or []
    if params:
        p_rows = []
        for p in params[:10]:
            old_v = f'{p["old_value"]:.4f}' if p.get("old_value") is not None else "—"
            new_v = f'{p["new_value"]:.4f}' if p.get("new_value") is not None else "—"
            ctx = p.get("context") or ""
            ts = p.get("timestamp", "")[:10] if p.get("timestamp") else ""
            p_rows.append([p.get("parameter", ""), f'{old_v} → {new_v}', p.get("unit", ""), ctx, ts])
        body += section("On-Chain Parameter Changes",
                        table(["Parameter", "Change", "Unit", "Context", "Date"], p_rows, []))
    else:
        body += section("On-Chain Parameter Changes",
                        '<p class="meta"><em>No parameter changes detected in the last 30 days.</em></p>')

    # Oracle Behavior
    oracle = d.get("oracle_behavior") or {}
    feeds = oracle.get("feeds_monitored") or []
    stress = oracle.get("stress_events") or []
    if feeds:
        f_rows = []
        for f in feeds:
            dev = f'{f["max_deviation_pct"]:.2f}%' if f.get("max_deviation_pct") is not None else "—"
            lat = f'{f["mean_latency_s"]:.0f}s' if f.get("mean_latency_s") is not None else "—"
            f_rows.append([f.get("feed", ""), f.get("provider", ""), str(f.get("reading_count", 0)), dev, lat])
        oracle_html = table(["Feed", "Provider", "Readings", "Max Dev", "Avg Latency"], f_rows, [2])
        if stress:
            oracle_html += f'<p style="color:#c0392b"><strong>{len(stress)} stress event(s) in 90-day window</strong></p>'
        body += section("Oracle Behavior", oracle_html)
    elif oracle.get("note"):
        body += section("Oracle Behavior",
                        f'<p class="meta"><em>{oracle["note"]}</em></p>')
    else:
        body += section("Oracle Behavior",
                        '<p class="meta"><em>Not yet monitored.</em></p>')

    # Contagion — shared depositor exposure
    contagion = d.get("contagion") or {}
    con_wallets = contagion.get("wallets") or []
    shared = contagion.get("shared_protocols") or {}
    if con_wallets:
        c_rows = []
        for cw in con_wallets[:10]:
            rs = f'{cw["risk_score"]:.0f}' if cw.get("risk_score") is not None else "—"
            exp = fmt_usd(cw.get("exposure_usd"))
            others = ", ".join(cw.get("other_protocols", [])[:3]) or "none"
            c_rows.append([cw.get("address", ""), exp, rs, others])
        con_html = table(["Wallet", "Exposure", "Risk", "Also in"], c_rows, [1])
        if shared:
            con_html += '<p class="meta">Shared depositor overlap: '
            con_html += ", ".join(f"{k} ({v})" for k, v in list(shared.items())[:5])
            con_html += "</p>"
        body += section(f"Contagion — Shared Depositors ({contagion.get('wallets_analyzed', 0)} analyzed)", con_html)
    elif contagion.get("note"):
        body += section("Contagion", f'<p class="meta"><em>{contagion["note"]}</em></p>')

    # Divergence Signals
    div_signals = d.get("divergence_signals") or []
    if div_signals:
        ds_rows = [[s.get("type", ""), s.get("severity", ""), s.get("summary", "")[:80], s.get("timestamp", "")[:10] if s.get("timestamp") else ""] for s in div_signals[:10]]
        body += section("Divergence Signals", table(["Type", "Severity", "Summary", "Date"], ds_rows, []))
    else:
        body += section("Divergence Signals",
                        '<p class="meta"><em>No divergence signals captured for this protocol in 90-day window.</em></p>')

    # Contract Surveillance
    surv = d.get("surveillance") or {}
    surv_contracts = surv.get("contracts") or []
    surv_upgrades = surv.get("upgrade_events") or []
    if surv_contracts:
        sc_rows = []
        for sc in surv_contracts:
            flags = []
            if sc.get("admin_keys"): flags.append("admin")
            if sc.get("upgradeable"): flags.append("proxy")
            if sc.get("pausable"): flags.append("pause")
            tl = f'{sc["timelock_hours"]:.0f}h' if sc.get("timelock_hours") else "—"
            ms = sc.get("multisig") or "—"
            sc_rows.append([sc.get("address", "")[:14] + "...", sc.get("chain", ""), " ".join(flags), tl, ms])
        surv_html = table(["Contract", "Chain", "Flags", "Timelock", "Multisig"], sc_rows, [])
        if surv_upgrades:
            surv_html += f'<p style="color:#c0392b"><strong>{len(surv_upgrades)} upgrade(s) detected</strong></p>'
        body += section("Contract Surveillance", surv_html)
    elif surv.get("note"):
        body += section("Contract Surveillance", f'<p class="meta"><em>{surv["note"]}</em></p>')
    else:
        body += section("Contract Surveillance",
                        '<p class="meta"><em>Not yet monitored.</em></p>')

    # Sanctions
    sanctions = d.get("sanctions") or {}
    related = sanctions.get("related_issuer_screenings") or []
    if related:
        san_rows = [[r.get("issuer", ""), str(r.get("targets_configured", 0)), r.get("latest", "—")] for r in related]
        body += section("Sanctions Screening",
                        f'<p class="meta">{sanctions.get("note", "")}</p>' +
                        table(["Issuer", "Targets", "Latest"], san_rows, []))
    else:
        body += section("Sanctions Screening",
                        f'<p class="meta"><em>{sanctions.get("note", "Screening data not available for this entity.")}</em></p>')

    # Evidence links
    evidence = f'<a href="{d.get("proof_url", "#")}" style="color:#0B090A">PSI Proof page</a><br>'
    evidence += f'<a href="/witness" style="color:#0B090A">Witness — issuer evidence</a>'
    body += section("Evidence", evidence)

    body += attestation_footer(report_hash, d.get("formula_version", ""),
                               timestamp, lens_result.get("lens_id") if lens_result else None,
                               lens_result.get("lens_version") if lens_result else None)

    cat_count = len(d.get("category_scores") or {})
    exp_count = len(d.get("exposures") or d.get("holdings") or [])
    return page(f"{name} — Protocol Risk Report", body,
                f"Protocol risk report for {name}. PSI {score:.1f}/100." if score else f"Protocol risk report for {name}.",
                f"{CANONICAL_BASE_URL}/report/protocol/{d.get('entity_id', '')}",
                form_id="FORM PSI-RPT-001 · BASIS PROTOCOL",
                stats=[f"PSI {score:.1f}" if score else "PSI —", f"{cat_count} categories", f"{exp_count} exposures"])


def _render_lens_section(lens_result: dict) -> str:
    framework = lens_result.get("framework", "")
    overall = lens_result.get("overall_pass", False)
    status_cls = "pass" if overall else "fail"
    status_label = "PASS" if overall else "FAIL"

    html = f'<div class="section"><h3>Regulatory Classification — {framework}</h3>'
    html += f'<p>Overall: <span class="{status_cls}" style="font-weight:700">{status_label}</span></p>'

    for group_id, group in (lens_result.get("classification") or {}).items():
        html += f'<p style="font-weight:600;margin-bottom:4px">{group_id.replace("_", " ").title()}</p>'
        for c in group.get("criteria", []):
            pill = "pill-pass" if c["passed"] else "pill-fail"
            label = "PASS" if c["passed"] else "FAIL"
            html += f'<div style="margin:2px 0"><span class="pill {pill}">{label}</span> {c["name"]}'
            if c.get("threshold"):
                html += f' <span class="meta">(threshold: {c["threshold"]})</span>'
            html += '</div>'

    html += '</div>'
    return html
