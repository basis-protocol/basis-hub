"""
Composition Engine
===================
Composes indices (SII, PSI) into composite risk views (CQI).
All scores computed on-demand — no storage.
"""

import math

from app.database import fetch_all, fetch_one
from app.scoring import score_to_grade


def compose_geometric_mean(scores):
    """Geometric mean — penalizes weakness in any component."""
    if not scores or any(s is None or s <= 0 for s in scores):
        return None
    product = 1.0
    for s in scores:
        product *= s
    return round(product ** (1.0 / len(scores)), 2)


def compose_weighted_average(scores, weights=None):
    """Weighted average — linear blend."""
    if not scores:
        return None
    if weights is None:
        weights = [1.0] * len(scores)
    total = sum(s * w for s, w in zip(scores, weights) if s is not None)
    weight_sum = sum(w for s, w in zip(scores, weights) if s is not None)
    return round(total / weight_sum, 2) if weight_sum > 0 else None


def compose_minimum(scores):
    """Minimum — only as strong as weakest link."""
    valid = [s for s in scores if s is not None]
    return min(valid) if valid else None


def compute_cqi(asset_symbol, protocol_slug):
    """
    Compute Collateral Quality Index for an asset-in-protocol pair.
    Fetches SII and PSI scores from the database on demand.
    """
    # Get SII score from scores table joined to stablecoins
    sii_row = fetch_one("""
        SELECT s.overall_score, s.grade
        FROM scores s
        JOIN stablecoins st ON st.id = s.stablecoin_id
        WHERE UPPER(st.symbol) = UPPER(%s)
    """, (asset_symbol,))

    if not sii_row or sii_row.get("overall_score") is None:
        return {"error": f"SII score not found for {asset_symbol}"}

    # Get PSI score
    psi_row = fetch_one("""
        SELECT overall_score, grade, protocol_name
        FROM psi_scores
        WHERE protocol_slug = %s
        ORDER BY computed_at DESC
        LIMIT 1
    """, (protocol_slug,))

    if not psi_row or psi_row.get("overall_score") is None:
        return {"error": f"PSI score not found for {protocol_slug}. Run PSI scoring first."}

    sii_score = float(sii_row["overall_score"])
    psi_score = float(psi_row["overall_score"])
    cqi_score = compose_geometric_mean([sii_score, psi_score])

    return {
        "composite_id": "cqi",
        "name": "Collateral Quality Index",
        "asset": asset_symbol.upper(),
        "protocol": psi_row.get("protocol_name", protocol_slug),
        "protocol_slug": protocol_slug,
        "cqi_score": cqi_score,
        "cqi_grade": score_to_grade(cqi_score) if cqi_score else None,
        "inputs": {
            "sii": {"score": sii_score, "grade": sii_row.get("grade")},
            "psi": {"score": psi_score, "grade": psi_row.get("grade")},
        },
        "method": "geometric_mean",
        "formula_version": "composition-v1.0.0",
    }


def compute_cqi_matrix():
    """Compute CQI for all stablecoin x protocol combinations."""
    stablecoins = fetch_all("""
        SELECT st.symbol, s.overall_score, s.grade
        FROM scores s
        JOIN stablecoins st ON st.id = s.stablecoin_id
        WHERE s.overall_score IS NOT NULL
        ORDER BY s.overall_score DESC
    """)

    protocols = fetch_all("""
        SELECT DISTINCT ON (protocol_slug)
            protocol_slug, protocol_name, overall_score, grade
        FROM psi_scores
        ORDER BY protocol_slug, computed_at DESC
    """)

    if not protocols:
        return {"error": "No PSI scores available. Run PSI scoring first.", "matrix": []}

    matrix = []
    for coin in stablecoins:
        for proto in protocols:
            sii = float(coin["overall_score"]) if coin.get("overall_score") else None
            psi = float(proto["overall_score"]) if proto.get("overall_score") else None
            if sii and psi:
                cqi = compose_geometric_mean([sii, psi])
                matrix.append({
                    "asset": coin["symbol"],
                    "protocol": proto.get("protocol_name", proto["protocol_slug"]),
                    "protocol_slug": proto["protocol_slug"],
                    "cqi_score": cqi,
                    "cqi_grade": score_to_grade(cqi) if cqi else None,
                    "sii_score": sii,
                    "psi_score": psi,
                })

    matrix.sort(key=lambda x: x.get("cqi_score", 0), reverse=True)
    return {"matrix": matrix, "count": len(matrix)}
