"""
Verification Agent — Classifier
=================================
Assigns severity (silent/notable/alert/critical) and broadcast flag
to assessment events. Includes divergence detection.
"""

import logging
from app.agent.config import AGENT_CONFIG

logger = logging.getLogger(__name__)


def detect_divergence(assessment: dict, previous: dict | None) -> bool:
    """
    Returns True if money is moving toward assets with declining scores.

    Divergence = any holding where:
        1. pct_of_wallet increased (capital flowed in), AND
        2. sii_7d_delta < 0 (the asset's quality is declining)

    Only triggers if the asset's SII is also below the ceiling (default: 80).
    """
    if previous is None:
        return False

    ceiling = AGENT_CONFIG["divergence_sii_ceiling"]

    prev_holdings = previous.get("holdings_snapshot") or []
    prev_by_symbol = {}
    for h in prev_holdings:
        if isinstance(h, dict):
            prev_by_symbol[h.get("symbol", "").upper()] = h

    current_holdings = assessment.get("holdings_snapshot") or []

    for h in current_holdings:
        if not isinstance(h, dict):
            continue
        symbol = h.get("symbol", "").upper()
        sii_score = h.get("sii_score")
        sii_delta = h.get("sii_7d_delta", 0)
        pct = h.get("pct_of_wallet", 0)

        if sii_score is None:
            continue

        prev_h = prev_by_symbol.get(symbol, {})
        prev_pct = prev_h.get("pct_of_wallet", 0)

        # Capital flowed in AND quality declining AND score below ceiling
        if pct > prev_pct and sii_delta < 0 and sii_score < ceiling:
            logger.info(
                f"Divergence detected: {symbol} exposure increased "
                f"{prev_pct:.1f}% -> {pct:.1f}% while SII declining "
                f"(7d delta: {sii_delta}, score: {sii_score})"
            )
            return True

    return False


def classify_severity(
    assessment: dict,
    previous: dict | None,
    config: dict | None = None,
) -> tuple[str, bool]:
    """
    Returns (severity, broadcast_worthy).

    Rules:
    - silent:   No material change. Daily cycle with delta <1 pt.
    - notable:  Score movement 1-3 pts. Moderate activity. Included in daily pulse.
    - alert:    Capital flowing toward deteriorating quality. Score delta >3 pts.
                Concentration spike. Broadcast immediately.
    - critical: Depeg event >1%. Score drop >5 pts in 24h. Broadcast + on-chain.
    """
    if config is None:
        config = AGENT_CONFIG

    trigger = assessment.get("trigger_type", "")
    score = assessment.get("wallet_risk_score")
    prev_score = assessment.get("wallet_risk_score_prev")
    hhi = assessment.get("concentration_hhi")
    prev_hhi = assessment.get("concentration_hhi_prev")

    # Compute score delta
    score_delta = 0
    if score is not None and prev_score is not None:
        score_delta = abs(score - prev_score)

    # Critical: depeg event
    if trigger == "depeg":
        detail = assessment.get("trigger_detail") or {}
        deviation = abs(detail.get("deviation_pct", 0))
        if deviation >= config["critical_depeg_pct"]:
            return ("critical", True)

    # Critical: large score drop
    if score is not None and prev_score is not None:
        if (prev_score - score) >= config["critical_score_delta_pts"]:
            return ("critical", True)

    # Alert: divergence detected
    has_divergence = detect_divergence(assessment, previous)
    if has_divergence:
        return ("alert", True)

    # Alert: score delta exceeds threshold
    if score_delta >= config["alert_score_delta_pts"]:
        return ("alert", True)

    # Alert: concentration spike
    if trigger == "concentration_shift":
        return ("alert", True)

    # Notable: moderate score movement
    if score_delta >= 1.0:
        return ("notable", False)

    # Notable: large movement trigger
    if trigger == "large_movement":
        return ("notable", False)

    # Notable: auto_promote
    if trigger == "auto_promote":
        return ("notable", False)

    # Silent: daily cycle or no material change
    return ("silent", False)
