"""
Report Data Assembler
======================
Assembles structured report data from existing scoring primitives.
No new scoring logic — reports compose existing SII, PSI, CQI, and wallet scores.
"""

import logging
from datetime import datetime, timezone

from app.database import fetch_one, fetch_all
from app.scoring import FORMULA_VERSION, SII_V1_WEIGHTS, STRUCTURAL_SUBWEIGHTS
from app.composition import compose_geometric_mean

logger = logging.getLogger(__name__)


def assemble_report_data(entity_type: str, entity_id: str, persist: bool = True) -> dict | None:
    """
    Assemble full report data for an entity.

    Args:
        entity_type: 'stablecoin', 'protocol', or 'wallet'
        entity_id: stablecoin symbol, protocol slug, or wallet address
        persist: If True, compute hash and store in report_attestations

    Returns:
        Structured dict with all data needed to render any template,
        or None if entity not found.
    """
    if entity_type == "stablecoin":
        report = _assemble_stablecoin(entity_id)
    elif entity_type == "protocol":
        report = _assemble_protocol(entity_id)
    elif entity_type == "wallet":
        report = _assemble_wallet(entity_id)
    else:
        return None

    if report and persist:
        try:
            from app.report_attestation import compute_report_hash, store_report_attestation
            timestamp = report.get("computed_at") or datetime.now(timezone.utc).isoformat()
            report_hash = compute_report_hash(
                report, "protocol_risk", None, None, timestamp,
                state_hashes=report.get("state_hashes"),
            )
            store_report_attestation(
                entity_type=entity_type,
                entity_id=entity_id,
                template="protocol_risk",
                lens=None,
                lens_version=None,
                report_hash=report_hash,
                score_hashes=report.get("score_hashes", []),
                cqi_hashes=report.get("cqi_hashes"),
                methodology_version=report.get("formula_version", FORMULA_VERSION),
            )
            report["report_hash"] = report_hash
        except Exception as e:
            logger.warning(f"Report attestation failed for {entity_type}/{entity_id}: {e}")

    return report


def _assemble_stablecoin(symbol: str) -> dict | None:
    """Assemble SII report for a stablecoin."""
    row = fetch_one("""
        SELECT s.*, st.name, st.symbol, st.issuer, st.contract AS token_contract
        FROM scores s
        JOIN stablecoins st ON st.id = s.stablecoin_id
        WHERE UPPER(st.symbol) = UPPER(%s)
    """, (symbol,))

    if not row:
        return None

    sid = row["stablecoin_id"]
    score = float(row.get("overall_score") or 0)

    categories = {
        "peg": {"score": _f(row.get("peg_score")), "weight": SII_V1_WEIGHTS["peg_stability"]},
        "liquidity": {"score": _f(row.get("liquidity_score")), "weight": SII_V1_WEIGHTS["liquidity_depth"]},
        "flows": {"score": _f(row.get("mint_burn_score")), "weight": SII_V1_WEIGHTS["mint_burn_dynamics"]},
        "distribution": {"score": _f(row.get("distribution_score")), "weight": SII_V1_WEIGHTS["holder_distribution"]},
        "structural": {"score": _f(row.get("structural_score")), "weight": SII_V1_WEIGHTS["structural_risk_composite"]},
    }

    structural_breakdown = {
        "reserves": {"score": _f(row.get("reserves_score")), "weight": STRUCTURAL_SUBWEIGHTS["reserves_collateral"]},
        "contract": {"score": _f(row.get("contract_score")), "weight": STRUCTURAL_SUBWEIGHTS["smart_contract_risk"]},
        "oracle": {"score": _f(row.get("oracle_score")), "weight": STRUCTURAL_SUBWEIGHTS["oracle_integrity"]},
        "governance": {"score": _f(row.get("governance_score")), "weight": STRUCTURAL_SUBWEIGHTS["governance_operations"]},
        "network": {"score": _f(row.get("network_score")), "weight": STRUCTURAL_SUBWEIGHTS["network_chain_risk"]},
    }

    components = fetch_all("""
        SELECT DISTINCT ON (component_id)
            component_id, category, raw_value, normalized_score, data_source, collected_at
        FROM component_readings
        WHERE stablecoin_id = %s AND collected_at > NOW() - INTERVAL '48 hours'
        ORDER BY component_id, collected_at DESC
    """, (sid,))

    # Protocols that hold this stablecoin
    protocols_holding = _get_protocols_for_stablecoin(symbol)

    # Score hashes from assessment events
    score_hashes = _get_score_hashes("stablecoin", sid)

    # State attestation hashes
    state_hashes = _get_state_hashes(["sii_components", "cda_extractions"], entity_id=sid)

    # History for temporal stability
    history = fetch_all("""
        SELECT overall_score, grade, score_date AS computed_at
        FROM score_history WHERE stablecoin = %s
        ORDER BY score_date DESC LIMIT 30
    """, (sid,))

    return {
        "entity_type": "stablecoin",
        "entity_id": symbol.upper(),
        "name": row.get("name", symbol),
        "symbol": (row.get("symbol") or symbol).upper(),
        "issuer": row.get("issuer"),
        "token_contract": row.get("token_contract"),
        "score": score,
        "categories": categories,
        "structural_breakdown": structural_breakdown,
        "components": [_fmt_component(c) for c in components],
        "component_count": row.get("component_count") or len(components),
        "protocols_holding": protocols_holding,
        "score_hashes": score_hashes,
        "state_hashes": state_hashes,
        "history": [{"score": float(h["overall_score"]),
                      "date": h["computed_at"].isoformat()} for h in history] if history else [],
        "formula_version": row.get("formula_version") or FORMULA_VERSION,
        "computed_at": row["computed_at"].isoformat() if row.get("computed_at") else None,
        "proof_url": f"/proof/sii/{sid}",
    }


def _assemble_protocol(slug: str) -> dict | None:
    """Assemble PSI report for a protocol, including stablecoin exposure and CQI."""
    import time as _t

    _timings = {}

    _t0 = _t.monotonic()
    row = fetch_one("""
        SELECT id, protocol_slug, protocol_name, overall_score, grade,
               category_scores, component_scores, raw_values,
               formula_version, inputs_hash, computed_at
        FROM psi_scores
        WHERE protocol_slug = %s
        ORDER BY computed_at DESC LIMIT 1
    """, (slug,))
    _timings["psi_score"] = round((_t.monotonic() - _t0) * 1000)

    if not row:
        return None

    score = float(row.get("overall_score") or 0)
    cat_scores = row.get("category_scores") or {}
    comp_scores = row.get("component_scores") or {}

    _t0 = _t.monotonic()
    exposure = _get_stablecoin_exposure(slug)
    _timings["exposure"] = round((_t.monotonic() - _t0) * 1000)

    # CQI pairs — batched: PSI score already in hand, SII scores from exposure query
    _t0 = _t.monotonic()
    cqi_pairs = []
    if exposure:
        psi_score = score
        psi_comp_scores = comp_scores
        from app.composition import compose_geometric_mean, _sii_confidence, _psi_confidence, _lower_confidence
        psi_conf = _psi_confidence(psi_comp_scores)
        for coin in exposure:
            sii = coin.get("sii_score")
            if sii is None or sii <= 0 or psi_score <= 0:
                continue
            cqi_score_val = compose_geometric_mean([sii, psi_score])
            if cqi_score_val is None:
                continue
            sii_conf = _sii_confidence(39)
            cqi_conf = _lower_confidence(sii_conf, psi_conf)
            cqi_pairs.append({
                "asset": coin["symbol"],
                "protocol": row.get("protocol_name", slug),
                "sii_score": sii,
                "psi_score": psi_score,
                "cqi_score": cqi_score_val,
                "confidence": cqi_conf["confidence"],
                "proof_url": f"/proof/sii/{coin.get('stablecoin_id', coin['symbol'])}",
            })
    _timings["cqi"] = round((_t.monotonic() - _t0) * 1000)

    # Prompt 1 composers — RPI, governance, parameters, oracle
    _t0 = _t.monotonic()
    rpi = _get_rpi(slug)
    _timings["rpi"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    governance_activity = _get_governance_activity(slug)
    _timings["governance"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    parameter_changes = _get_parameter_changes(slug)
    _timings["parameters"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    oracle_behavior = _get_oracle_behavior(slug)
    _timings["oracle"] = round((_t.monotonic() - _t0) * 1000)

    # Prompt 2 composers — contagion, divergence, surveillance, sanctions
    _t0 = _t.monotonic()
    contagion = _get_contagion(slug)
    _timings["contagion"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    divergence_signals = _get_divergence_signals(slug)
    _timings["divergence"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    surveillance = _get_surveillance(slug)
    _timings["surveillance"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    sanctions = _get_sanctions(slug)
    _timings["sanctions"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    score_hashes = _get_score_hashes("protocol", slug)
    _timings["score_hashes"] = round((_t.monotonic() - _t0) * 1000)

    _t0 = _t.monotonic()
    state_hashes = _get_state_hashes(["psi_components", "psi_discoveries"], entity_id=slug)
    _timings["state_hashes"] = round((_t.monotonic() - _t0) * 1000)

    _total = sum(_timings.values())
    logger.error(
        f"[report] _assemble_protocol({slug}): {_total}ms total — "
        + ", ".join(f"{k}={v}ms" for k, v in _timings.items())
    )

    return {
        "entity_type": "protocol",
        "entity_id": slug,
        "name": row.get("protocol_name", slug),
        "protocol_slug": slug,
        "score": score,
        "category_scores": cat_scores,
        "component_scores": comp_scores,
        "raw_values": row.get("raw_values") or {},
        "exposure": exposure,
        "cqi_pairs": cqi_pairs,
        "rpi": rpi,
        "governance_activity": governance_activity,
        "parameter_changes": parameter_changes,
        "oracle_behavior": oracle_behavior,
        "contagion": contagion,
        "divergence_signals": divergence_signals,
        "surveillance": surveillance,
        "sanctions": sanctions,
        "score_hashes": score_hashes,
        "state_hashes": state_hashes,
        "formula_version": row.get("formula_version") or "psi-v0.2.0",
        "inputs_hash": row.get("inputs_hash"),
        "computed_at": row["computed_at"].isoformat() if row.get("computed_at") else None,
        "proof_url": f"/proof/psi/{slug}",
        "_timings": _timings,
    }


def _assemble_wallet(address: str) -> dict | None:
    """Assemble wallet risk report from holdings and scores."""
    addr = address.strip().lower()

    risk = fetch_one("""
        SELECT risk_score, risk_grade, concentration_hhi, concentration_grade,
               unscored_pct, coverage_quality,
               num_scored_holdings, num_unscored_holdings, num_total_holdings,
               dominant_asset, dominant_asset_pct,
               total_stablecoin_value, size_tier, formula_version, computed_at
        FROM wallet_graph.wallet_risk_scores
        WHERE LOWER(wallet_address) = %s
        ORDER BY computed_at DESC LIMIT 1
    """, (addr,))

    holdings = fetch_all("""
        SELECT token_address, symbol, chain, balance, value_usd,
               is_scored, sii_score, sii_grade, pct_of_wallet
        FROM wallet_graph.wallet_holdings
        WHERE LOWER(wallet_address) = %s
          AND indexed_at > NOW() - INTERVAL '7 days'
          AND value_usd >= 0.01
        ORDER BY value_usd DESC
    """, (addr,))

    if not risk and not holdings:
        return None

    holdings_value = sum(float(h.get("value_usd") or 0) for h in holdings)

    # Recalculate pct_of_wallet from current holdings
    for h in holdings:
        h["pct_of_wallet"] = round((float(h.get("value_usd") or 0) / holdings_value) * 100, 2) if holdings_value > 0 else 0

    # Collect proof URLs for scored holdings
    for h in holdings:
        if h.get("is_scored") and h.get("symbol"):
            sid = fetch_one(
                "SELECT id FROM stablecoins WHERE UPPER(symbol) = UPPER(%s)",
                (h["symbol"],),
            )
            h["proof_url"] = f"/proof/sii/{sid['id']}" if sid else None

    score_hashes = _get_score_hashes("wallet", addr)
    state_hashes = _get_state_hashes(["wallets", "wallet_profiles", "edges"])

    return {
        "entity_type": "wallet",
        "entity_id": addr,
        "address": addr,
        "score": float(risk["risk_score"]) if risk and risk.get("risk_score") is not None else None,
        "concentration_hhi": float(risk["concentration_hhi"]) if risk and risk.get("concentration_hhi") else None,
        "unscored_pct": float(risk["unscored_pct"]) if risk and risk.get("unscored_pct") else None,
        "coverage_quality": risk.get("coverage_quality") if risk else None,
        "dominant_asset": risk.get("dominant_asset") if risk else None,
        "dominant_asset_pct": float(risk["dominant_asset_pct"]) if risk and risk.get("dominant_asset_pct") else None,
        "size_tier": risk.get("size_tier") if risk else None,
        "holdings_value": round(holdings_value, 2),
        "holdings": [{
            "symbol": h.get("symbol"),
            "chain": h.get("chain", "ethereum"),
            "value_usd": float(h.get("value_usd") or 0),
            "pct_of_wallet": h.get("pct_of_wallet"),
            "is_scored": h.get("is_scored"),
            "sii_score": float(h["sii_score"]) if h.get("sii_score") is not None else None,
            "proof_url": h.get("proof_url"),
        } for h in holdings],
        "num_scored": risk.get("num_scored_holdings") if risk else sum(1 for h in holdings if h.get("is_scored")),
        "num_unscored": risk.get("num_unscored_holdings") if risk else sum(1 for h in holdings if not h.get("is_scored")),
        "score_hashes": score_hashes,
        "state_hashes": state_hashes,
        "formula_version": risk.get("formula_version") if risk else "wallet-v1.0.0",
        "computed_at": risk["computed_at"].isoformat() if risk and risk.get("computed_at") else None,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_state_hashes(domains: list[str], entity_id: str = None) -> dict:
    """Fetch latest state attestation hashes for relevant domains."""
    try:
        from app.state_attestation import get_latest_attestation
        hashes = {}
        for domain in domains:
            att = get_latest_attestation(domain, entity_id)
            if att:
                hashes[domain] = att["batch_hash"]
        return hashes
    except Exception:
        return {}


def _f(val) -> float | None:
    """Safe float conversion."""
    return round(float(val), 2) if val is not None else None


def _fmt_component(c: dict) -> dict:
    """Format a component reading for report data."""
    src = (c.get("data_source") or "").lower()
    if "cda" in src:
        source_type = "cda_extraction"
    elif src in ("static", "config"):
        source_type = "static_config"
    else:
        source_type = "live_api"

    return {
        "id": c["component_id"],
        "category": c["category"],
        "raw_value": c.get("raw_value"),
        "normalized_score": round(float(c["normalized_score"]), 2) if c.get("normalized_score") is not None else None,
        "data_source": c.get("data_source"),
        "source_type": source_type,
        "collected_at": c["collected_at"].isoformat() if c.get("collected_at") else None,
    }


def _get_protocols_for_stablecoin(symbol: str) -> list[dict]:
    """Find protocols that hold or accept this stablecoin."""
    try:
        rows = fetch_all("""
            SELECT DISTINCT ON (ps.protocol_slug)
                ps.protocol_slug, ps.protocol_name, ps.overall_score, ps.grade
            FROM psi_scores ps
            JOIN protocol_collateral_exposure ce ON ce.protocol_slug = ps.protocol_slug
            WHERE UPPER(ce.token_symbol) = UPPER(%s)
              AND ce.is_stablecoin = TRUE
            ORDER BY ps.protocol_slug, ps.computed_at DESC
        """, (symbol,))
        return [{"slug": r["protocol_slug"], "name": r["protocol_name"],
                 "psi_score": float(r["overall_score"]) if r.get("overall_score") else None} for r in rows]
    except Exception:
        return []


def _get_stablecoin_exposure(protocol_slug: str) -> list[dict]:
    """Get stablecoins held/accepted by a protocol."""
    try:
        rows = fetch_all("""
            SELECT ce.token_symbol AS asset_symbol, ce.tvl_usd AS exposure_usd,
                   s.overall_score, s.grade, st.id AS stablecoin_id, st.name
            FROM protocol_collateral_exposure ce
            LEFT JOIN stablecoins st ON UPPER(st.symbol) = UPPER(ce.token_symbol)
            LEFT JOIN scores s ON s.stablecoin_id = st.id
            WHERE ce.protocol_slug = %s
              AND ce.is_stablecoin = TRUE
            ORDER BY ce.tvl_usd DESC NULLS LAST
        """, (protocol_slug,))
        return [{
            "symbol": r["asset_symbol"],
            "stablecoin_id": r.get("stablecoin_id"),
            "name": r.get("name"),
            "exposure_usd": float(r["exposure_usd"]) if r.get("exposure_usd") else None,
            "sii_score": float(r["overall_score"]) if r.get("overall_score") else None,
        } for r in rows]
    except Exception:
        return []


def _get_score_hashes(entity_type: str, entity_id: str) -> list[str]:
    """Get score hashes from component_batch_hashes or assessment_events."""
    try:
        if entity_type in ("stablecoin", "protocol"):
            rows = fetch_all("""
                SELECT DISTINCT batch_hash FROM component_batch_hashes
                WHERE entity_type = %s AND entity_id = %s
                  AND batch_hash IS NOT NULL
                ORDER BY batch_hash
            """, (entity_type, entity_id))
            return [r["batch_hash"] for r in rows] if rows else []
        elif entity_type == "wallet":
            rows = fetch_all("""
                SELECT DISTINCT content_hash FROM assessment_events
                WHERE LOWER(wallet_address) = %s
                  AND content_hash IS NOT NULL
                ORDER BY content_hash
            """, (entity_id,))
            return [r["content_hash"] for r in rows] if rows else []
        return []
    except Exception:
        return []


# =============================================================================
# Protocol composers — Prompt 1: RPI, governance, parameters, oracle
# =============================================================================

def _get_rpi(slug: str) -> dict | None:
    """Latest RPI score with 30d/90d trajectory."""
    try:
        row = fetch_one("""
            SELECT overall_score, grade, component_scores, raw_values,
                   inputs_hash, methodology_version, computed_at
            FROM rpi_scores
            WHERE protocol_slug = %s
            ORDER BY computed_at DESC LIMIT 1
        """, (slug,))
        if not row:
            return None

        score = float(row["overall_score"]) if row.get("overall_score") else None

        # Trajectory — fetch prior scores for 30d and 90d deltas
        trajectory = {}
        for label, days in [("30d", 30), ("90d", 90)]:
            prior = fetch_one("""
                SELECT overall_score FROM rpi_scores
                WHERE protocol_slug = %s AND computed_at < NOW() - INTERVAL '%s days'
                ORDER BY computed_at DESC LIMIT 1
            """, (slug, days))
            if prior and prior.get("overall_score") and score is not None:
                trajectory[label] = round(score - float(prior["overall_score"]), 2)

        return {
            "score": score,
            "grade": row.get("grade"),
            "component_scores": row.get("component_scores") or {},
            "raw_values": row.get("raw_values") or {},
            "inputs_hash": row.get("inputs_hash"),
            "methodology_version": row.get("methodology_version"),
            "computed_at": row["computed_at"].isoformat() if row.get("computed_at") else None,
            "trajectory": trajectory,
        }
    except Exception as e:
        logger.warning(f"_get_rpi({slug}) failed: {e}")
        return None


def _get_governance_activity(slug: str, days: int = 30) -> dict:
    """Governance proposals and events for this protocol in the last N days."""
    result = {"proposals_count": 0, "edited_after_publication": [], "recent_high_impact": []}
    try:
        # Count recent proposals
        count_row = fetch_one("""
            SELECT COUNT(*) as cnt FROM governance_proposals
            WHERE protocol_slug = %s
              AND COALESCE(captured_at, scraped_at, created_at) > NOW() - INTERVAL '%s days'
        """, (slug, days))
        result["proposals_count"] = count_row["cnt"] if count_row else 0

        # Proposals with detected edits after publication
        edits = fetch_all("""
            SELECT proposal_id, title, first_capture_body_hash, body_hash, body_changed
            FROM governance_proposals
            WHERE protocol_slug = %s AND body_changed = TRUE
            ORDER BY COALESCE(captured_at, scraped_at, created_at) DESC
            LIMIT 10
        """, (slug,))
        if edits:
            result["edited_after_publication"] = [
                {"proposal_id": r["proposal_id"], "title": r.get("title", ""),
                 "original_hash": r.get("first_capture_body_hash"),
                 "current_hash": r.get("body_hash")}
                for r in edits
            ]

        # Recent high-impact events
        events = fetch_all("""
            SELECT event_type, title, description, outcome, event_timestamp
            FROM governance_events
            WHERE protocol_slug = %s
              AND event_timestamp > NOW() - INTERVAL '%s days'
            ORDER BY event_timestamp DESC
            LIMIT 5
        """, (slug, days))
        if events:
            result["recent_high_impact"] = [
                {"type": r["event_type"], "title": r.get("title", ""),
                 "description": r.get("description", ""), "outcome": r.get("outcome"),
                 "timestamp": r["event_timestamp"].isoformat() if r.get("event_timestamp") else None}
                for r in events
            ]
    except Exception as e:
        logger.warning(f"_get_governance_activity({slug}) failed: {e}")
    return result


def _get_parameter_changes(slug: str, days: int = 30) -> list:
    """Recent on-chain parameter changes for this protocol."""
    try:
        rows = fetch_all("""
            SELECT parameter_name, parameter_key, asset_symbol,
                   previous_value, new_value, value_unit,
                   change_magnitude, change_direction, change_context,
                   transaction_hash, changed_at
            FROM protocol_parameter_changes
            WHERE protocol_slug = %s
              AND changed_at > NOW() - INTERVAL '%s days'
            ORDER BY changed_at DESC
            LIMIT 20
        """, (slug, days))
        if not rows:
            return []
        return [
            {
                "parameter": r["parameter_name"],
                "key": r.get("parameter_key"),
                "asset": r.get("asset_symbol"),
                "old_value": float(r["previous_value"]) if r.get("previous_value") is not None else None,
                "new_value": float(r["new_value"]) if r.get("new_value") is not None else None,
                "unit": r.get("value_unit"),
                "magnitude": float(r["change_magnitude"]) if r.get("change_magnitude") is not None else None,
                "direction": r.get("change_direction"),
                "context": r.get("change_context"),
                "tx_hash": r.get("transaction_hash"),
                "timestamp": r["changed_at"].isoformat() if r.get("changed_at") else None,
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"_get_parameter_changes({slug}) failed: {e}")
        return []


def _get_oracle_behavior(slug: str, days: int = 90) -> dict:
    """Oracle feed behavior for feeds used by this protocol."""
    result = {"feeds_monitored": [], "stress_events": []}
    try:
        # Find feeds mapped to this protocol via oracle_registry
        feeds = fetch_all("""
            SELECT oracle_address, oracle_name, oracle_provider, chain, asset_symbol
            FROM oracle_registry
            WHERE is_active = TRUE
              AND (entity_slug = %s OR entity_type = 'stablecoin')
        """, (slug,))

        if not feeds:
            result["note"] = "Oracle feed mapping not configured for this protocol"
            return result

        for feed in feeds:
            addr = feed["oracle_address"]
            # Aggregate readings over the window
            agg = fetch_one("""
                SELECT COUNT(*) as reading_count,
                       AVG(ABS(deviation_pct)) as mean_deviation,
                       MAX(ABS(deviation_pct)) as max_deviation,
                       AVG(latency_seconds) as mean_latency
                FROM oracle_price_readings
                WHERE oracle_address = %s
                  AND recorded_at > NOW() - INTERVAL '%s days'
            """, (addr, days))

            result["feeds_monitored"].append({
                "feed": feed.get("oracle_name", addr),
                "provider": feed.get("oracle_provider"),
                "asset": feed["asset_symbol"],
                "reading_count": agg["reading_count"] if agg else 0,
                "mean_deviation_pct": round(float(agg["mean_deviation"]), 4) if agg and agg.get("mean_deviation") else None,
                "max_deviation_pct": round(float(agg["max_deviation"]), 4) if agg and agg.get("max_deviation") else None,
                "mean_latency_s": round(float(agg["mean_latency"]), 1) if agg and agg.get("mean_latency") else None,
            })

        # Stress events in window
        stress = fetch_all("""
            SELECT oracle_name, asset_symbol, event_type, event_start,
                   duration_seconds, max_deviation_pct, max_latency_seconds
            FROM oracle_stress_events
            WHERE event_start > NOW() - INTERVAL '%s days'
            ORDER BY event_start DESC
            LIMIT 10
        """, (days,))
        if stress:
            result["stress_events"] = [
                {
                    "feed": r.get("oracle_name"),
                    "asset": r["asset_symbol"],
                    "type": r.get("event_type"),
                    "timestamp": r["event_start"].isoformat() if r.get("event_start") else None,
                    "duration_s": r.get("duration_seconds"),
                    "max_deviation_pct": float(r["max_deviation_pct"]) if r.get("max_deviation_pct") else None,
                    "max_latency_s": r.get("max_latency_seconds"),
                }
                for r in stress
            ]
    except Exception as e:
        logger.warning(f"_get_oracle_behavior({slug}) failed: {e}")
        result["note"] = f"Oracle behavior query failed: {e}"
    return result


# =============================================================================
# Protocol composers — Prompt 2: contagion, divergence, surveillance, sanctions
# =============================================================================

def _get_contagion(slug: str, top_n: int = 20) -> dict:
    """Top depositors/LPs for this protocol and their cross-protocol exposure."""
    result = {"wallets": [], "shared_protocols": {}}
    try:
        wallets = fetch_all("""
            SELECT pw.wallet_address, pw.balance,
                   r.risk_score, r.total_stablecoin_value
            FROM protocol_pool_wallets pw
            LEFT JOIN wallet_graph.wallet_risk_scores r
                ON LOWER(pw.wallet_address) = LOWER(r.wallet_address)
            WHERE pw.protocol_slug = %s
            ORDER BY pw.balance DESC NULLS LAST
            LIMIT %s
        """, (slug, top_n))

        if not wallets:
            result["note"] = "No pool wallet data captured for this protocol"
            return result

        protocol_overlap = {}
        for w in wallets:
            addr = w["wallet_address"]
            display = f"{addr[:6]}...{addr[-4:]}" if len(addr) >= 10 else addr

            # Cross-protocol exposure for this wallet
            other_protocols = fetch_all("""
                SELECT DISTINCT protocol_slug FROM protocol_pool_wallets
                WHERE LOWER(wallet_address) = LOWER(%s) AND protocol_slug != %s
            """, (addr, slug))
            others = [r["protocol_slug"] for r in (other_protocols or [])]
            for op in others:
                protocol_overlap[op] = protocol_overlap.get(op, 0) + 1

            result["wallets"].append({
                "address": display,
                "exposure_usd": float(w["balance"]) if w.get("balance") else None,
                "risk_score": float(w["risk_score"]) if w.get("risk_score") else None,
                "other_protocols": others[:3],
                "protocol_count": len(others),
            })

        # Top shared protocols
        result["shared_protocols"] = dict(
            sorted(protocol_overlap.items(), key=lambda x: x[1], reverse=True)[:5]
        )
        result["wallets_analyzed"] = len(wallets)
    except Exception as e:
        logger.warning(f"_get_contagion({slug}) failed: {e}")
        result["note"] = f"Contagion analysis failed: {e}"
    return result


def _get_divergence_signals(slug: str, days: int = 90) -> list:
    """Discovery signals referencing this protocol."""
    try:
        rows = fetch_all("""
            SELECT signal_type, severity, detected_at, payload
            FROM discovery_signals
            WHERE detected_at > NOW() - INTERVAL '%s days'
              AND (
                  payload::text ILIKE %s
                  OR payload::text ILIKE %s
              )
            ORDER BY detected_at DESC
            LIMIT 20
        """, (days, f"%{slug}%", f"%{slug.replace('-', '_')}%"))
        if not rows:
            return []
        result = []
        for r in rows:
            payload = r.get("payload") or {}
            if isinstance(payload, str):
                import json
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            result.append({
                "type": r.get("signal_type"),
                "severity": r.get("severity"),
                "timestamp": r["detected_at"].isoformat() if r.get("detected_at") else None,
                "summary": payload.get("summary", payload.get("description", "")),
            })
        return result
    except Exception as e:
        logger.warning(f"_get_divergence_signals({slug}) failed: {e}")
        return []


def _get_surveillance(slug: str) -> dict:
    """Contract surveillance state for this protocol's contracts."""
    result = {"contracts": [], "upgrade_events": []}
    try:
        contracts = fetch_all("""
            SELECT entity_id, chain, contract_address,
                   has_admin_keys, is_upgradeable, has_pause_function,
                   timelock_hours, multisig_threshold, source_code_hash,
                   scanned_at
            FROM contract_surveillance
            WHERE entity_id = %s OR entity_id LIKE %s
            ORDER BY scanned_at DESC
        """, (slug, f"{slug}_%"))
        if contracts:
            seen = set()
            for c in contracts:
                key = (c["entity_id"], c["chain"], c["contract_address"])
                if key in seen:
                    continue
                seen.add(key)
                result["contracts"].append({
                    "entity_id": c["entity_id"],
                    "chain": c["chain"],
                    "address": c["contract_address"],
                    "admin_keys": c.get("has_admin_keys", False),
                    "upgradeable": c.get("is_upgradeable", False),
                    "pausable": c.get("has_pause_function", False),
                    "timelock_hours": float(c["timelock_hours"]) if c.get("timelock_hours") else None,
                    "multisig": c.get("multisig_threshold"),
                    "source_hash": c.get("source_code_hash"),
                    "scanned_at": c["scanned_at"].isoformat() if c.get("scanned_at") else None,
                })

        # Contract upgrade history
        upgrades = fetch_all("""
            SELECT entity_symbol, contract_address, chain,
                   previous_bytecode_hash, current_bytecode_hash,
                   upgrade_detected_at
            FROM contract_upgrade_history
            WHERE entity_symbol = %s
               OR contract_address IN (
                   SELECT contract_address FROM contract_surveillance WHERE entity_id = %s
               )
            ORDER BY upgrade_detected_at DESC
            LIMIT 10
        """, (slug, slug))
        if upgrades:
            result["upgrade_events"] = [
                {
                    "contract": u["contract_address"],
                    "chain": u["chain"],
                    "previous_hash": u.get("previous_bytecode_hash"),
                    "current_hash": u.get("current_bytecode_hash"),
                    "detected_at": u["upgrade_detected_at"].isoformat() if u.get("upgrade_detected_at") else None,
                }
                for u in upgrades
            ]
    except Exception as e:
        logger.warning(f"_get_surveillance({slug}) failed: {e}")
        result["note"] = f"Surveillance query failed: {e}"
    return result


def _get_sanctions(slug: str, days: int = 180) -> dict:
    """Sanctions screening history for this protocol's contracts and wallets."""
    result = {"note": "Sanctions screening scoped to issuers/wallets, not protocols directly"}
    try:
        # Check if any stablecoins this protocol holds have issuer screening
        exposure = _get_stablecoin_exposure(slug)
        related = []
        for coin in (exposure or []):
            symbol = coin.get("symbol")
            if symbol:
                screening = fetch_one("""
                    SELECT COUNT(*) as cnt, MAX(created_at) as latest
                    FROM sanctions_screen_targets
                    WHERE entity_symbol = %s
                """, (symbol.lower(),))
                if screening and screening.get("cnt", 0) > 0:
                    related.append({
                        "issuer": symbol,
                        "targets_configured": screening["cnt"],
                        "latest": screening["latest"].isoformat() if screening.get("latest") else None,
                    })
        if related:
            result["related_issuer_screenings"] = related
    except Exception as e:
        logger.warning(f"_get_sanctions({slug}) failed: {e}")
    return result
