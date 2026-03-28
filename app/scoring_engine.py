"""
Generic Scoring Engine
=======================
Scores any entity using an index definition dict.
Reuses normalization functions from app/scoring.py — no duplication.

Pattern: raw values -> normalize per component -> aggregate by category -> weighted sum = score.
"""

from app.scoring import (
    normalize_inverse_linear, normalize_linear, normalize_log,
    normalize_centered, normalize_exponential_penalty, normalize_direct,
    score_to_grade,
)

NORMALIZATION_FUNCTIONS = {
    "inverse_linear": normalize_inverse_linear,
    "linear": normalize_linear,
    "log": normalize_log,
    "centered": normalize_centered,
    "exponential_penalty": normalize_exponential_penalty,
    "direct": normalize_direct,
}


def score_entity(definition, raw_values):
    """
    Score an entity using an index definition.

    Args:
        definition: An index definition dict (see app/index_definitions/schema.py)
        raw_values: Dict of component_id -> raw numeric value

    Returns dict with: index_id, version, overall_score, grade,
        category_scores, component_scores, components_available,
        components_total, coverage
    """
    # Step 1: Normalize each component
    component_scores = {}
    for comp_id, comp_def in definition["components"].items():
        if comp_id in raw_values and raw_values[comp_id] is not None:
            fn_name = comp_def["normalization"]["function"]
            fn = NORMALIZATION_FUNCTIONS.get(fn_name)
            if fn:
                params = comp_def["normalization"]["params"]
                try:
                    component_scores[comp_id] = round(fn(raw_values[comp_id], **params), 2)
                except Exception:
                    pass

    # Step 2: Aggregate by category (weighted average within category)
    category_scores = {}
    for cat_id, cat_def in definition["categories"].items():
        cat_components = {
            cid: cdef for cid, cdef in definition["components"].items()
            if cdef["category"] == cat_id
        }
        total = 0.0
        weight_used = 0.0
        for cid, cdef in cat_components.items():
            if cid in component_scores:
                total += component_scores[cid] * cdef["weight"]
                weight_used += cdef["weight"]
        if weight_used > 0:
            category_scores[cat_id] = round(total / weight_used, 2)

    # Step 3: Weighted sum across categories
    overall = 0.0
    cat_weight_used = 0.0
    for cat_id, cat_def in definition["categories"].items():
        weight = cat_def["weight"] if isinstance(cat_def, dict) else 0
        if cat_id in category_scores:
            overall += category_scores[cat_id] * weight
            cat_weight_used += weight

    if cat_weight_used > 0 and cat_weight_used < 1.0:
        overall = overall / cat_weight_used

    overall = round(overall, 2)

    return {
        "index_id": definition["index_id"],
        "version": definition["version"],
        "overall_score": overall,
        "grade": score_to_grade(overall),
        "category_scores": category_scores,
        "component_scores": component_scores,
        "components_available": len(component_scores),
        "components_total": len(definition["components"]),
        "coverage": round(len(component_scores) / max(len(definition["components"]), 1), 2),
    }
