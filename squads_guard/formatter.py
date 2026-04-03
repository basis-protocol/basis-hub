"""
Build the assessment response from scored data.
"""

from datetime import datetime, timezone

from .config import BASIS_API_URL, GRADE_EMOJI
from .scorer import get_score_value


def format_assessment(
    stablecoin_scores: dict[str, dict],
    protocol_scores: dict[str, dict],
    cqi_scores: dict[str, dict],
) -> dict:
    """Build structured assessment response."""
    lines: list[str] = []
    warnings: list[str] = []

    lines.append("\u2501\u2501\u2501 Basis Protocol Risk Assessment \u2501\u2501\u2501")
    lines.append("")

    # Protocol section
    if protocol_scores:
        for slug, psi in protocol_scores.items():
            score = get_score_value(psi)
            grade = psi.get("grade", "?")
            emoji = GRADE_EMOJI.get(grade, "\u26aa")
            name = slug.replace("-", " ").title()
            lines.append(f"Protocol: {name}")
            lines.append(f"  {emoji} PSI {score} ({grade})")
            if score < 50:
                warnings.append(f"\u26a0\ufe0f {name} PSI is below 50 \u2014 elevated protocol risk")
        lines.append("")

    # Stablecoin section
    if stablecoin_scores:
        lines.append("Stablecoins in transaction:")
        for coin_id, sii in stablecoin_scores.items():
            score = get_score_value(sii)
            grade = sii.get("grade", "?")
            emoji = GRADE_EMOJI.get(grade, "\u26aa")
            symbol = coin_id.upper()
            lines.append(f"  {emoji} {symbol}: SII {score} ({grade})")
            if score < 60:
                warnings.append(f"\u26a0\ufe0f {symbol} SII is below 60 \u2014 stablecoin quality concern")
        lines.append("")

    # CQI section
    if cqi_scores:
        lines.append("Composed risk (CQI = \u221a(SII \u00d7 PSI)):")
        for pair_name, cqi_data in cqi_scores.items():
            cqi_val = cqi_data["cqi"]
            cqi_grade = cqi_data["grade"]
            sii_val = cqi_data["sii"]
            emoji = GRADE_EMOJI.get(cqi_grade, "\u26aa")
            lines.append(f"  {emoji} {pair_name}: CQI {cqi_val} ({cqi_grade})")

            gap = sii_val - cqi_val
            if gap > 15:
                warnings.append(
                    f"\u26a0\ufe0f {pair_name}: CQI is {gap:.0f} points below SII \u2014 "
                    f"protocol risk is significantly reducing stablecoin quality"
                )
        lines.append("")

    # Warnings
    if warnings:
        lines.append("\u26a0\ufe0f WARNINGS:")
        for w in warnings:
            lines.append(f"  {w}")
        lines.append("")

    # Footer
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"Scored at: {now}")
    lines.append(f"Source: {BASIS_API_URL}")
    lines.append("\u2501" * 38)

    # Determine status
    all_scores: list[float] = []
    if cqi_scores:
        all_scores.extend(c["cqi"] for c in cqi_scores.values())
    elif stablecoin_scores:
        all_scores.extend(get_score_value(s) for s in stablecoin_scores.values())

    if not all_scores:
        status = "no_data"
    elif any(s < 50 for s in all_scores):
        status = "warning"
    elif any(s < 65 for s in all_scores):
        status = "caution"
    else:
        status = "pass"

    return {
        "status": status,
        "summary": "\n".join(lines),
        "warnings": warnings,
        "scores": {
            "stablecoins": {k: get_score_value(v) for k, v in stablecoin_scores.items()},
            "protocols": {k: get_score_value(v) for k, v in protocol_scores.items()},
            "cqi": {k: v["cqi"] for k, v in cqi_scores.items()},
        },
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "source": BASIS_API_URL,
    }
