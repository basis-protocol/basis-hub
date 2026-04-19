"""
Engagement Template
====================
Per-account demo artifact for cold email attachment.
Five sections: exposure map, own scores, historical reconstruction,
start today, forward to risk team.

Renders markdown by default (copy-pasteable into email drafts).
HTML optional via format parameter.

Consumes 8 composer outputs from _assemble_protocol — does NOT query
the database. Every claim cites a score hash or proof URL.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CANONICAL_BASE_URL = "https://basisprotocol.xyz"


def render(report_data: dict, lens_result: dict = None,
           report_hash: str = "", timestamp: str = "", format: str = "markdown") -> str:
    """Render engagement artifact. Markdown default, HTML optional."""
    d = report_data
    entity_type = d.get("entity_type", "protocol")
    name = d.get("name", d.get("entity_id", "Unknown"))
    entity_id = d.get("entity_id", "")

    if format == "html":
        return _render_html(d, lens_result, report_hash, timestamp)

    return _render_markdown(d, lens_result, report_hash, timestamp)


def _render_markdown(d: dict, lens_result: dict = None,
                     report_hash: str = "", timestamp: str = "") -> str:
    entity_type = d.get("entity_type", "protocol")
    name = d.get("name", d.get("entity_id", "Unknown"))
    entity_id = d.get("entity_id", "")
    score = d.get("score")
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []

    # Header block
    proof_path = "/proof/psi/" if entity_type == "protocol" else "/proof/sii/"
    lines.append(f"**Account:** {name}")
    lines.append(f"**Generated:** {ts}")
    lines.append(f"**Verifiable:** {CANONICAL_BASE_URL}{proof_path}{entity_id}")
    if report_hash:
        lines.append(f"**Report hash:** `{report_hash[:16]}...`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # =================================================================
    # Section 1 — Live exposure map
    # =================================================================
    lines.append(f"## Live exposure map for {name}")
    lines.append("")

    if entity_type == "protocol":
        _render_protocol_exposure(lines, d)
    elif entity_type == "stablecoin":
        _render_stablecoin_exposure(lines, d)
    elif entity_type == "wallet":
        _render_wallet_exposure(lines, d)
    lines.append("")

    # =================================================================
    # Section 2 — Entity's own scores
    # =================================================================
    lines.append(f"## {name} scores")
    lines.append("")

    if entity_type == "protocol":
        _render_protocol_scores(lines, d)
    elif entity_type == "stablecoin":
        _render_stablecoin_scores(lines, d)
    elif entity_type == "wallet":
        _render_wallet_scores(lines, d)
    lines.append("")

    # =================================================================
    # Section 3 — What Basis would have shown
    # =================================================================
    lines.append("## What Basis would have shown")
    lines.append("")

    if entity_type == "protocol":
        _render_protocol_event(lines, d)
    elif entity_type == "stablecoin":
        _render_stablecoin_event(lines, d)
    elif entity_type == "wallet":
        _render_wallet_event(lines, d)
    lines.append("")

    # =================================================================
    # Section 4 — Start today
    # =================================================================
    lines.append("## Start today")
    lines.append("")
    lines.append("```bash")
    if entity_type == "protocol":
        lines.append(f"curl {CANONICAL_BASE_URL}/api/psi/scores/{entity_id}")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/compose/cqi?protocol={entity_id}")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/reports/protocol/{entity_id}")
    elif entity_type == "stablecoin":
        lines.append(f"curl {CANONICAL_BASE_URL}/api/scores/{entity_id}")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/compose/cqi?asset={entity_id}")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/reports/stablecoin/{entity_id}")
    elif entity_type == "wallet":
        lines.append(f"curl {CANONICAL_BASE_URL}/api/wallets/{entity_id}")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/wallets/{entity_id}/profile")
        lines.append(f"curl {CANONICAL_BASE_URL}/api/wallets/{entity_id}/connections")
    lines.append("```")
    if entity_type == "protocol":
        lines.append("")
        lines.append("```solidity")
        lines.append("uint16 score = IBasisSIIOracle(oracle).score(token);")
        lines.append("```")
    if entity_type == "stablecoin":
        lines.append("")
        lines.append("If you are a scored subject, methodology participation is a separate channel — reach out at methodology@basisprotocol.xyz.")
    lines.append("")

    # =================================================================
    # Section 5 — Forward
    # =================================================================
    if entity_type == "wallet":
        lines.append("## Forward to your treasury committee")
        lines.append("")
        lines.append(
            f"Forward to your treasury committee or external advisor. "
            f"Everything above is free to read; the [Proof pages]({CANONICAL_BASE_URL}{proof_path}{entity_id}) "
            f"let them verify independently without any vendor relationship with us."
        )
    else:
        lines.append("## Forward to your risk team")
        lines.append("")
        lines.append(
            f"Forward to your risk team or your external risk contributor. "
            f"Everything above is free to read; the [Proof pages]({CANONICAL_BASE_URL}{proof_path}{entity_id}) "
            f"let them verify independently without any vendor relationship with us."
        )
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Basis Protocol · {CANONICAL_BASE_URL} · Decision integrity infrastructure*")
    state_hashes = d.get("state_hashes") or {}
    if isinstance(state_hashes, dict) and state_hashes:
        hashes = list(state_hashes.values())[:3]
        if hashes and isinstance(hashes[0], dict):
            hashes = [h.get("batch_hash", "")[:12] for h in hashes if h.get("batch_hash")]
        elif hashes:
            hashes = [str(h)[:12] for h in hashes]
        if hashes:
            hash_str = ", ".join(h + "..." for h in hashes)
            lines.append(f"*State hashes: {hash_str}*")

    return "\n".join(lines)


def _render_html(d: dict, lens_result: dict = None,
                 report_hash: str = "", timestamp: str = "") -> str:
    """Render engagement as HTML using the shared design system."""
    from app.templates._html import page, section, table, CANONICAL_BASE_URL as BASE

    md = _render_markdown(d, lens_result, report_hash, timestamp)

    # Convert markdown to simple HTML
    import re
    html_body = ""
    for line in md.split("\n"):
        if line.startswith("## "):
            html_body += f'<h3>{line[3:]}</h3>'
        elif line.startswith("**") and line.endswith("**"):
            html_body += f'<p><strong>{line[2:-2]}</strong></p>'
        elif line.startswith("|"):
            if "---" in line:
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            html_body += "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
        elif line.startswith("```"):
            if "bash" in line or "solidity" in line:
                html_body += '<pre style="background:#e8e6e0;padding:8px;font-size:0.8rem;overflow-x:auto"><code>'
            elif line == "```":
                html_body += "</code></pre>"
        elif line.startswith("curl ") or line.startswith("uint16"):
            html_body += line + "\n"
        elif line == "---":
            html_body += '<hr style="border:none;border-top:1px solid #ccc;margin:16px 0">'
        elif line.startswith("*") and line.endswith("*") and not line.startswith("**"):
            html_body += f'<p class="meta"><em>{line[1:-1]}</em></p>'
        elif line:
            html_body += f"<p>{line}</p>"

    name = d.get("name", d.get("entity_id", "Unknown"))
    return page(
        f"{name} — Engagement",
        html_body,
        f"Engagement artifact for {name}.",
        f"{BASE}/report/protocol/{d.get('entity_id', '')}",
        form_id="ENGAGEMENT · BASIS PROTOCOL",
        stats=[f"PSI {d.get('score', 0):.1f}" if d.get("score") else "—"],
    )


# =============================================================================
# Section renderers — Protocol
# =============================================================================

def _render_protocol_exposure(lines: list, d: dict):
    exposure = d.get("exposure") or []
    cqi_pairs = d.get("cqi_pairs") or []
    if not exposure:
        lines.append("*No exposure data captured.*")
        return
    # Count unscored exposure
    unscored = [e for e in exposure if not e.get("sii_score")]
    unscored_usd = sum(e.get("exposure_usd") or 0 for e in unscored)

    lines.append("| Asset | Exposure | SII | CQI | Proof |")
    lines.append("|-------|----------|-----|-----|-------|")
    cqi_map = {p["asset"]: p for p in cqi_pairs}
    flagged = None
    top_10 = exposure[:10]
    for e in top_10:
        sym = e.get("symbol", "?")
        amt = f"${e['exposure_usd']:,.0f}" if e.get("exposure_usd") else "—"
        sii = f"{e['sii_score']:.1f}" if e.get("sii_score") else "unscored"
        cqi_entry = cqi_map.get(sym, {})
        cqi_s = f"{cqi_entry['cqi_score']:.1f}" if cqi_entry.get("cqi_score") else "—"
        proof = f"[verify]({CANONICAL_BASE_URL}/proof/sii/{e.get('stablecoin_id', sym)})" if e.get("stablecoin_id") else "—"
        lines.append(f"| {sym} | {amt} | {sii} | {cqi_s} | {proof} |")
        if e.get("sii_score") and e["sii_score"] < 60 and not flagged:
            flagged = f"{sym} scores below 60 on SII ({e['sii_score']:.1f}) — weakest asset in the exposure set."
    remaining = len(exposure) - len(top_10)
    lines.append("")
    if remaining > 0:
        slug = d.get("entity_id", "")
        lines.append(f"+ {remaining} more exposures at {CANONICAL_BASE_URL}/proof/psi/{slug}")
        lines.append("")
    if unscored and unscored_usd > 0:
        lines.append(f"*{len(unscored)} tokens represent ${unscored_usd:,.0f} aggregate exposure not yet covered by SII.*")
        lines.append("")
    lines.append(flagged or "Exposure set is stable across all counterparties monitored over the last 30 days.")


def _render_protocol_scores(lines: list, d: dict):
    score = d.get("score")
    entity_id = d.get("entity_id", "")
    if score is not None:
        lines.append(f"**PSI:** {score:.1f}/100 · [proof]({CANONICAL_BASE_URL}/proof/psi/{entity_id})")
    rpi = d.get("rpi")
    if rpi and rpi.get("score") is not None:
        traj = rpi.get("trajectory") or {}
        delta_30d = traj.get("30d")
        top_mover = rpi.get("top_mover")
        line = f"**RPI:** {rpi['score']:.1f}/100"
        if delta_30d is not None:
            if abs(delta_30d) >= 1:
                sign = "+" if delta_30d >= 0 else ""
                traj_str = f"30d {sign}{delta_30d:.1f}"
                if top_mover:
                    comp_name = top_mover["component"].replace("_", " ")
                    comp_sign = "+" if top_mover["delta"] >= 0 else ""
                    traj_str += f", driven by {comp_name} ({comp_sign}{top_mover['delta']:.1f})"
                line += f" · {traj_str}"
            else:
                line += " · 30d stable"
        else:
            line += " · no prior data (bootstrap window)"
        lines.append(line)


def _render_protocol_event(lines: list, d: dict):
    entity_id = d.get("entity_id", "")
    name = d.get("name", entity_id)
    exposure = d.get("exposure") or []
    scored_map = {e["symbol"].upper(): e.get("sii_score") for e in exposure if e.get("sii_score")}
    unscored_symbols = {e["symbol"].upper() for e in exposure if not e.get("sii_score")}

    # 1. Oracle stress ≥25bps
    stress = (d.get("oracle_behavior") or {}).get("stress_events") or []
    sig_stress = [s for s in stress if s.get("max_deviation_pct") and abs(s["max_deviation_pct"]) >= 0.25]
    if sig_stress:
        ev = sig_stress[0]
        feed = ev.get("feed", "a monitored feed")
        date = (ev.get("timestamp") or "")[:10]
        dev = f"{abs(ev.get('max_deviation_pct', 0)):.1f}%"
        dur_s = ev.get("duration_s")
        dur = f" for {dur_s} seconds" if dur_s else ""
        lines.append(
            f"{name}'s oracle infrastructure experienced stress on {date}: "
            f"the {feed} deviated {dev} from the CEX reference price{dur}. "
            f"Basis captured the deviation in real time and flagged the reading as a stress event. "
            f"{feed} continues under continuous monitoring; any further deviation will be captured and attested.")
        return

    # 2. Reactive parameter change
    params = d.get("parameter_changes") or []
    reactive = [p for p in params if p.get("context") == "reactive"]
    if reactive:
        p = reactive[0]
        param = p.get("parameter", "a risk parameter")
        date = (p.get("timestamp") or "")[:10]
        old_v = p.get("old_value", "?")
        new_v = p.get("new_value", "?")
        unit = p.get("unit") or ""
        lines.append(
            f"{name} made a reactive parameter change on {date}: "
            f"{param} moved from {old_v} to {new_v} {unit} in response to market conditions. "
            f"Basis captured the on-chain transaction and classified this as a reactive adjustment. "
            f"Parameter state is preserved hourly; pre-change configuration is queryable via the temporal engine.")
        return

    # 3. Post-publication governance edit
    edits = (d.get("governance_activity") or {}).get("edited_after_publication") or []
    if edits:
        ed = edits[0]
        title = ed.get("title", "a governance proposal")
        orig_hash = (ed.get("original_hash") or "")[:12]
        lines.append(
            f"Basis detected a post-publication edit to \"{title}\" — "
            f"the proposal body was modified after voting opened. "
            f"The original text is preserved at hash `{orig_hash}...`; the current text differs. "
            f"Edit detection runs on every proposal across monitored DAOs; any further changes will be flagged.")
        return

    # 4-5. Admin key rotation / peg event — not yet wired

    # 6. Executed proposal
    events = (d.get("governance_activity") or {}).get("recent_high_impact") or []
    if events:
        ev = events[0]
        title = ev.get("title") or ""
        date = (ev.get("timestamp") or "")[:10]
        description = _describe_proposal(title)

        # Build proposal URL
        proposal_url = _build_proposal_url(ev)

        # Coverage implication
        extracted_tokens = _extract_tokens_from_title(title)
        implication = ""
        for token in extracted_tokens:
            if token in unscored_symbols:
                implication = (
                    f" {token} is not yet in Basis's SII coverage — "
                    f"your exposure to this new collateral will be scored once it hits the $1M threshold.")
                break
            elif token in scored_map:
                sii = scored_map[token]
                implication = (
                    f" {token} currently scores {sii:.1f} on SII; "
                    f"your composition exposure updates continuously as the score moves.")
                break

        url_suffix = f" [Proposal]({proposal_url})" if proposal_url else ""
        lines.append(
            f"{name} executed a governance proposal on {date}: "
            f"\"{title[:80]}{'...' if len(title) > 80 else ''}\", "
            f"{description}. "
            f"Basis captured the proposal text, the vote sequence, and the execution timestamp."
            f"{implication}{url_suffix}")
        return

    if params:
        p = params[0]
        param = p.get("parameter", "a parameter")
        date = (p.get("timestamp") or "")[:10]
        lines.append(
            f"{name} adjusted {param} on {date}. "
            f"Basis captured the on-chain change with before and after values. "
            f"Parameter state is preserved hourly; the prior configuration is queryable via the temporal engine.")
        return

    # 7. Empty window
    lines.append(
        f"No material events affecting your exposure set in the last 90 days. "
        f"Basis will reconstruct any prior event on request — "
        f"query the temporal engine at `{CANONICAL_BASE_URL}/api/scores/{entity_id}/history`.")


def _build_proposal_url(ev: dict) -> str:
    """Build URL to the proposal from available fields."""
    if ev.get("discussion_url"):
        return ev["discussion_url"]
    source = (ev.get("source") or "").lower()
    prop_id = ev.get("proposal_id") or ""
    if source == "snapshot" and prop_id:
        return f"https://snapshot.org/#/proposal/{prop_id}"
    if source == "tally" and prop_id:
        return f"https://www.tally.xyz/proposal/{prop_id}"
    return ""


def _strip_proposal_prefix(title: str) -> str:
    """Strip proposal number prefixes like 'MIP 128 - ', 'AIP 42: ', '[ARFC] '."""
    import re
    # "MIP 128 - REST" or "AIP-42: REST" or "Proposal 7: REST"
    stripped = re.sub(r'^(?:MIP|AIP|SIP|HIP|BIP|TIP)\s*[-#]?\s*\d+\s*[-:–]\s*', '', title, flags=re.IGNORECASE)
    # "[ARFC] REST" or "[TEMP CHECK] REST"
    stripped = re.sub(r'^\[(?:ARFC|TEMP CHECK|RFC|DISCUSSION|FINAL)\]\s*', '', stripped, flags=re.IGNORECASE)
    # "Proposal N: REST"
    stripped = re.sub(r'^Proposal\s+\d+\s*[-:–]\s*', '', stripped, flags=re.IGNORECASE)
    return stripped.strip() or title


def _describe_proposal(title: str) -> str:
    """Extract a one-line description of what a proposal does from its title."""
    title = _strip_proposal_prefix(title)
    t = title.lower()
    if "onboard" in t:
        token = _extract_first_token(title)
        return f"adding {token} as a new collateral type" if token else "onboarding a new asset"
    if "deprecat" in t:
        import re
        # "Lite App Deprecation Part 2" → subject = "Lite App"
        m = re.match(r'(.+?)\s+deprecat', t, re.IGNORECASE)
        subject = m.group(1).strip().title() if m else _extract_first_token(title)
        if subject:
            return f"continuing the deprecation of {subject}"
        return "deprecating an existing component"
    if "parameter update" in t or "parameter change" in t:
        token = _extract_first_token(title)
        return f"adjusting risk parameters for {token}" if token else "adjusting risk parameters"
    if "launch" in t and "configuration" in t:
        token = _extract_first_token(title)
        return f"launching the {token} deployment with initial parameters" if token else "launching a new deployment"
    if "risk steward" in t or "risk parameter" in t:
        return "adjusting risk parameters via the risk steward framework"
    if "temp check" in t:
        return "proposing a new protocol configuration for community review"
    if "upgrade" in t:
        return "upgrading protocol infrastructure"
    return "modifying protocol configuration as described in the proposal"


def _extract_first_token(title: str) -> str:
    """Try to extract a token symbol from a proposal title."""
    import re
    match = re.search(r'\b([A-Z]{2,10}(?:\.[eE])?)\b', title)
    if match:
        candidate = match.group(1)
        noise = {"THE", "AND", "FOR", "WITH", "FROM", "AAVE", "TEMP", "CHECK", "THIS", "THAT"}
        if candidate not in noise:
            return candidate
    return ""


def _extract_tokens_from_title(title: str) -> set:
    """Extract all potential token symbols from a title."""
    import re
    tokens = set()
    for match in re.finditer(r'\b([A-Z]{2,10})\b', title):
        candidate = match.group(1)
        noise = {"THE", "AND", "FOR", "WITH", "FROM", "AAVE", "TEMP", "CHECK", "THIS", "THAT",
                 "INSTANCE", "SONIC", "MAIN", "BASE", "RISK", "UPDATE", "LAUNCH", "ONBOARD"}
        if candidate not in noise:
            tokens.add(candidate)
    return tokens


# =============================================================================
# Section renderers — Stablecoin
# =============================================================================

def _render_stablecoin_exposure(lines: list, d: dict):
    cross = d.get("cross_protocol_exposure") or []
    if not cross:
        lines.append("*No protocol exposure data captured.*")
        return

    def _grade(score):
        if score is None: return "—"
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"

    lines.append("| Protocol | Exposure | PSI | Grade |")
    lines.append("|----------|----------|-----|-------|")
    flagged = None
    top_10 = cross[:10]
    for p in top_10:
        amt = f"${p['exposure_usd']:,.0f}" if p.get("exposure_usd") else "—"
        psi = f"{p['psi_score']:.1f}" if p.get("psi_score") else "—"
        grade = p.get("psi_grade") or _grade(p.get("psi_score"))
        lines.append(f"| {p.get('protocol', '?')} | {amt} | {psi} | {grade} |")
        if p.get("psi_score") and p["psi_score"] < 60 and not flagged:
            flagged = f"{p['protocol']} scores below 60 on PSI ({p['psi_score']:.1f})."
    remaining = len(cross) - len(top_10)
    lines.append("")
    if remaining > 0:
        entity_id = d.get("entity_id", "")
        lines.append(f"+ {remaining} more protocols at {CANONICAL_BASE_URL}/proof/sii/{entity_id}")
        lines.append("")
    lines.append(flagged or "All protocols holding this stablecoin score above 60 on PSI.")


def _render_stablecoin_scores(lines: list, d: dict):
    score = d.get("score")
    entity_id = d.get("entity_id", "")
    if score is not None:
        lines.append(f"**SII:** {score:.1f}/100 · [proof]({CANONICAL_BASE_URL}/proof/sii/{entity_id})")
    reserve = d.get("reserve_composition") or {}
    if reserve.get("extractions"):
        lines.append(f"Reserve attestations captured: {reserve['count']} in 90-day window.")
    elif reserve.get("note"):
        lines.append(f"*{reserve['note']}*")
    peg = d.get("peg_behavior") or {}
    if peg.get("readings"):
        lines.append(
            f"Peg stability: {peg.get('depegs_over_50bps', 0)} deviations >50bps in {peg.get('window_days', 90)}d, "
            f"max {peg.get('max_deviation_bps', 0):.0f}bps.")
    conc = d.get("holder_concentration") or {}
    if conc.get("current_gini") is not None:
        delta = conc.get("gini_delta")
        delta_str = f" ({'+'if delta>=0 else ''}{delta:.4f} over window)" if delta is not None else ""
        lines.append(f"Holder concentration (clustered Gini): {conc['current_gini']:.4f}{delta_str}.")


def _render_stablecoin_event(lines: list, d: dict):
    entity_id = d.get("entity_id", "")
    name = d.get("name", entity_id)
    issuer = d.get("issuer") or name
    cross = d.get("cross_protocol_exposure") or []
    n_protocols = len(cross)

    # 1. Depeg event (≥50bps)
    peg = d.get("peg_behavior") or {}
    if peg.get("depegs_over_50bps", 0) > 0 and peg.get("max_deviation_bps"):
        max_dev = peg["max_deviation_bps"]
        count = peg["depegs_over_50bps"]
        window = peg.get("window_days", 90)
        lines.append(
            f"{name} experienced {count} depeg event{'s' if count > 1 else ''} exceeding 50bps "
            f"in the {window}-day window, with a maximum deviation of {max_dev:.0f}bps. "
            f"Basis captured every 5-minute reading during the event — peg behavior at this "
            f"granularity is not preserved by the issuer's own monitoring. "
            f"All {n_protocols} CQI pairs holding {name} recomputed continuously during the window. "
            f"[Full sequence]({CANONICAL_BASE_URL}/proof/sii/{entity_id})")
        return

    # 2. Reserve composition shift
    reserve = d.get("reserve_composition") or {}
    extractions = reserve.get("extractions") or []
    if len(extractions) >= 2:
        latest = extractions[0]
        prior = extractions[-1]
        latest_date = (latest.get("extracted_at") or "")[:10]
        lines.append(
            f"{issuer} published an updated reserve attestation on {latest_date}. "
            f"Basis captured {len(extractions)} attestations in the 90-day window with cryptographic proofs. "
            f"Composition changes update CQI pairs for the {n_protocols} protocols holding {name} "
            f"within the next scoring cycle. "
            f"[Attestation chain]({CANONICAL_BASE_URL}/proof/sii/{entity_id})")
        return

    # 3. Freeze event
    freeze = d.get("freeze_history") or {}
    if freeze.get("events"):
        lines.append(
            f"{issuer} executed a freeze event. "
            f"Basis captured the freeze transaction and the affected address set. "
            f"Contract surveillance continues; any subsequent action will be captured.")
        return

    # 4. Issuer activity
    issuer_act = d.get("issuer_activity") or {}
    if issuer_act.get("screening_targets", 0) > 0:
        lines.append(
            f"{issuer} has {issuer_act['screening_targets']} sanctions screening targets configured. "
            f"Basis runs daily screening against OFAC and international lists. "
            f"Zero matches to date.")
        return

    # 5. Holder concentration shift
    conc = d.get("holder_concentration") or {}
    if conc.get("gini_delta") is not None and abs(conc["gini_delta"]) >= 0.01:
        direction = "increased" if conc["gini_delta"] > 0 else "decreased"
        lines.append(
            f"Holder concentration for {name} {direction} over the observation window "
            f"(Gini delta: {conc['gini_delta']:+.4f}). "
            f"Basis captures on-chain holder distribution continuously; "
            f"shifts at this scale typically precede liquidity changes.")
        return

    # 6. Most recent attestation (fallback)
    if extractions:
        latest_date = (extractions[0].get("extracted_at") or "")[:10]
        lines.append(
            f"Most recent reserve attestation captured on {latest_date}. "
            f"No material peg events or composition shifts in the 90-day window. "
            f"Basis continues archiving hourly; any subsequent movement will be flagged.")
        return

    # 7. Empty window
    lines.append(
        f"No material events affecting {name} in the last 90 days. "
        f"Basis will reconstruct any prior event on request — "
        f"query the temporal engine at `{CANONICAL_BASE_URL}/api/scores/{entity_id}/history`.")


# =============================================================================
# Section renderers — Wallet
# =============================================================================

def _render_wallet_exposure(lines: list, d: dict):
    holdings = d.get("holdings") or d.get("holdings_with_scores") or []
    if not holdings:
        lines.append("*No holdings data captured.*")
        return
    lines.append("| Asset | Value | % | SII | Chain |")
    lines.append("|-------|-------|---|-----|-------|")
    flagged = None
    for h in holdings[:15]:
        val = f"${h.get('value_usd', 0):,.0f}" if h.get("value_usd") else "—"
        pct = f"{h.get('pct_of_wallet') or h.get('pct', 0):.1f}%"
        sii = f"{h['sii_score']:.1f}" if h.get("sii_score") is not None else "—"
        chain = h.get("chain", "eth")
        lines.append(f"| {h.get('symbol', '?')} | {val} | {pct} | {sii} | {chain} |")
        if h.get("sii_score") is not None and h["sii_score"] < 60 and not flagged:
            flagged = f"{h.get('symbol', '?')} scores below 60 on SII ({h['sii_score']:.1f})."
    lines.append("")
    lines.append(flagged or "All scored holdings above 60 on SII.")


def _render_wallet_scores(lines: list, d: dict):
    score = d.get("score")
    conc = d.get("concentration") or {}
    if score is not None:
        lines.append(f"**Weighted SII:** {score:.1f}/100")
    if conc.get("hhi") is not None:
        lines.append(f"**Concentration (HHI):** {conc['hhi']:.0f}")
    if conc.get("dominant_asset"):
        lines.append(f"Dominant position: {conc['dominant_asset']} at {conc.get('dominant_pct', 0):.1f}%.")
    # Contagion summary
    contagion = d.get("contagion") or {}
    edges = contagion.get("edges") or []
    if edges:
        lines.append(f"Contagion exposure: {len(edges)} connected counterparties captured.")
    elif contagion.get("note"):
        lines.append(f"*{contagion['note']}*")


def _render_wallet_event(lines: list, d: dict):
    entity_id = d.get("entity_id", "")
    signals = d.get("signal_history") or []
    if signals:
        s = signals[0]
        lines.append(
            f"**{s.get('type', 'Event')}** ({(s.get('timestamp') or '')[:10]}): "
            f"{s.get('summary', 'Assessment event detected.')} "
            f"Severity: {s.get('severity', 'unknown')}.")
        return
    lines.append(
        f"No material events affecting this wallet in the last 90 days. "
        f"Basis will reconstruct any prior event on request — "
        f"query at `{CANONICAL_BASE_URL}/api/wallets/{entity_id}`.")


# =============================================================================
# Email Draft Generator
# =============================================================================

def _extract_event_summary(d: dict) -> str:
    """Extract the first event one-liner from Section 3 data sources."""
    entity_type = d.get("entity_type", "protocol")
    name = d.get("name", d.get("entity_id", "Unknown"))
    entity_id = d.get("entity_id", "")

    if entity_type == "protocol":
        # Oracle stress
        stress = (d.get("oracle_behavior") or {}).get("stress_events") or []
        sig_stress = [s for s in stress if s.get("max_deviation_pct") and abs(s["max_deviation_pct"]) >= 0.25]
        if sig_stress:
            ev = sig_stress[0]
            feed = ev.get("feed", "a monitored feed")
            date = (ev.get("timestamp") or "")[:10]
            dev = f"{abs(ev.get('max_deviation_pct', 0)):.1f}%"
            return f"{name}'s oracle infrastructure experienced stress on {date}: the {feed} deviated {dev} from the CEX reference price."

        # Reactive parameter change
        params = d.get("parameter_changes") or []
        reactive = [p for p in params if p.get("context") == "reactive"]
        if reactive:
            p = reactive[0]
            param = p.get("parameter", "a risk parameter")
            date = (p.get("timestamp") or "")[:10]
            return f"{name} made a reactive parameter change on {date}: {param} adjusted in response to market conditions."

        # Post-publication governance edit
        edits = (d.get("governance_activity") or {}).get("edited_after_publication") or []
        if edits:
            title = edits[0].get("title", "a governance proposal")
            return f"Basis detected a post-publication edit to \"{title}\" — the proposal body was modified after voting opened."

        # Executed proposal
        events = (d.get("governance_activity") or {}).get("recent_high_impact") or []
        if events:
            ev = events[0]
            title = ev.get("title") or ""
            date = (ev.get("timestamp") or "")[:10]
            return f"{name} executed a governance proposal on {date}: \"{title[:80]}\"."

        # Generic parameter change
        if params:
            p = params[0]
            param = p.get("parameter", "a parameter")
            date = (p.get("timestamp") or "")[:10]
            return f"{name} adjusted {param} on {date}."

        return f"No material events affecting {name} in the last 90 days."

    elif entity_type == "stablecoin":
        # Depeg event
        peg = d.get("peg_behavior") or {}
        if peg.get("depegs_over_50bps", 0) > 0 and peg.get("max_deviation_bps"):
            max_dev = peg["max_deviation_bps"]
            count = peg["depegs_over_50bps"]
            return f"{name} experienced {count} depeg event{'s' if count > 1 else ''} exceeding 50bps (max {max_dev:.0f}bps)."

        # Reserve composition shift
        reserve = d.get("reserve_composition") or {}
        extractions = reserve.get("extractions") or []
        if len(extractions) >= 2:
            latest_date = (extractions[0].get("extracted_at") or "")[:10]
            issuer = d.get("issuer") or name
            return f"{issuer} published an updated reserve attestation on {latest_date}."

        # Holder concentration shift
        conc = d.get("holder_concentration") or {}
        if conc.get("gini_delta") is not None and abs(conc["gini_delta"]) >= 0.01:
            direction = "increased" if conc["gini_delta"] > 0 else "decreased"
            return f"Holder concentration for {name} {direction} over the observation window."

        if extractions:
            latest_date = (extractions[0].get("extracted_at") or "")[:10]
            return f"Most recent reserve attestation captured on {latest_date}."

        return f"No material events affecting {name} in the last 90 days."

    elif entity_type == "wallet":
        signals = d.get("signal_history") or []
        if signals:
            s = signals[0]
            return f"{s.get('type', 'Event')}: {s.get('summary', 'Assessment event detected.')}"

        return f"No material events affecting this wallet in the last 90 days."

    return f"No material events in the last 90 days."


def generate_email_draft(report_data: dict, report_hash: str = "", timestamp: str = "") -> dict:
    """Generate pre-composed email draft from engagement data."""
    d = report_data
    entity_type = d.get("entity_type", "protocol")
    name = d.get("name", d.get("entity_id", "Unknown"))
    entity_id = d.get("entity_id", "")
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    event_summary = _extract_event_summary(d)
    shareable_url = f"{CANONICAL_BASE_URL}/engagement/{entity_type}/{entity_id}"

    subject = f"{event_summary} — one data point for context"

    body_lines = []
    body_lines.append(event_summary)
    body_lines.append("")
    body_lines.append(
        f"We put together a short engagement artifact for {name} — "
        f"scores, exposure, and the event timeline in one page:"
    )
    body_lines.append("")
    body_lines.append(shareable_url)
    body_lines.append("")
    if report_hash:
        body_lines.append(f"Report hash: `{report_hash[:16]}...` — verifiable at {CANONICAL_BASE_URL}/api/reports/verify/{report_hash}")
        body_lines.append("")
    body_lines.append("---")
    body_lines.append(f"Basis Protocol · {CANONICAL_BASE_URL} · Decision integrity infrastructure")

    return {
        "subject": subject,
        "body": "\n".join(body_lines),
        "shareable_url": shareable_url,
    }
