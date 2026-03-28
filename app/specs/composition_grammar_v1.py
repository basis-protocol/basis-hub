"""
BASIS-COMPOSITION-v1 Specification
====================================
Published rules for composing indices into composite risk views.
Composition is a protocol rule, not a product feature.
"""

COMPOSITION_GRAMMAR_V1 = {
    "version": "1.0.0",
    "compositions": [
        {
            "composite_id": "cqi",
            "name": "Collateral Quality Index",
            "formula_human": "CQI = sqrt(SII × PSI)",
            "description": "Quality of a stablecoin used as collateral in a specific protocol. Geometric mean penalizes weakness in either component.",
            "inputs": [
                {"index_id": "sii", "entity_type": "stablecoin", "role": "asset quality"},
                {"index_id": "psi", "entity_type": "protocol", "role": "venue quality"}
            ],
            "method": "geometric_mean",
            "example": "CQI(USDC in Aave) = sqrt(88.6 * 82.1) = 85.3"
        }
    ],
    "methods": {
        "geometric_mean": {
            "formula": "nth_root(product(scores))",
            "description": "Penalizes if either component is weak. A 95 and a 60 produce 75.5, not 77.5.",
            "use_when": "Both inputs must be strong for the composite to be strong."
        },
        "weighted_average": {
            "formula": "sum(weight_i * score_i) / sum(weight_i)",
            "description": "Linear blend. Forgiving of one weak component.",
            "use_when": "One input matters more than the other."
        },
        "minimum": {
            "formula": "min(scores)",
            "description": "Only as strong as the weakest link.",
            "use_when": "Failure in any component is disqualifying."
        }
    }
}
