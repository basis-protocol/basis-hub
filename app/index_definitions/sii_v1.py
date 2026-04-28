"""
SII v1.1.0 — Stablecoin Integrity Index expressed as an index definition.

This mirrors the canonical weights and component normalizations in app/scoring.py
but expresses them in the generic index definition format so SII dispatches
through the same aggregation registry as every other index.

v1.1.0 — aggregation migrated from the three-level legacy SII path
(components → legacy categories → structural subcategories → v1 categories →
overall) to the two-level registry model (components → v1 categories →
overall) with formula `coverage_weighted` and `min_coverage=0.0`.

The legacy three-level path is preserved in `app/scoring.py::calculate_sii` and
`calculate_structural_composite` and remains callable as the reference
implementation for `legacy_sii_v1` in `app.composition.AGGREGATION_FORMULAS`
so historical scores stay reproducible. `STRUCTURAL_SUBWEIGHTS` and
`DB_TO_STRUCTURAL_MAPPING` are now **legacy-only** — they do not participate
in the current-scoring overall. The per-subcategory structural scores
(reserves/contract/oracle/governance/network) continue to be stored on the
`scores` table as derived informational outputs; they no longer drive the
overall SII score.

See:
  - docs/methodology/aggregation_impact_analysis.md
  - docs/methodology/sii_changelog.md
  - docs/methodology/sii_wiring_acceptance.md
"""

from app.scoring import SII_V1_WEIGHTS, STRUCTURAL_SUBWEIGHTS, COMPONENT_NORMALIZATIONS

# Map Python function references to string names for the definition format
_FN_NAME_MAP = {
    "normalize_inverse_linear": "inverse_linear",
    "normalize_linear": "linear",
    "normalize_log": "log",
    "normalize_centered": "centered",
    "normalize_exponential_penalty": "exponential_penalty",
    "normalize_direct": "direct",
}


def _fn_to_name(fn) -> str:
    return _FN_NAME_MAP.get(fn.__name__, fn.__name__)


# Canonical legacy→v1 category mapping for SII components. `COMPONENT_NORMALIZATIONS`
# in `app/scoring.py` tags components with the 8-way legacy category vocabulary
# (peg_stability, liquidity, flows, market_activity, holder_distribution,
# smart_contract, governance, transparency, regulatory, network, reserves,
# oracle). `SII_V1_DEFINITION["categories"]` uses the 5-way v1 vocabulary
# (peg_stability, liquidity_depth, mint_burn_dynamics, holder_distribution,
# structural_risk_composite). For the registry's flat two-level aggregation to
# activate every v1 category, each component's `category` in the definition
# must be the v1 name. This table is the single source of truth for that
# mapping; it mirrors `LEGACY_TO_V1_MAPPING` in `app/scoring.py` used by the
# legacy three-level path. Keeping them in sync is a correctness invariant
# enforced by `tests/test_sii_wiring.py::test_legacy_and_v1_mappings_agree`.
SII_LEGACY_TO_V1_CATEGORY = {
    "peg_stability":      "peg_stability",
    "liquidity":          "liquidity_depth",
    "market_activity":    "mint_burn_dynamics",
    "flows":              "mint_burn_dynamics",
    "holder_distribution":"holder_distribution",
    "smart_contract":     "structural_risk_composite",
    "governance":         "structural_risk_composite",
    "transparency":       "structural_risk_composite",
    "regulatory":         "structural_risk_composite",
    "network":            "structural_risk_composite",
    "reserves":           "structural_risk_composite",
    "oracle":             "structural_risk_composite",
}


def _build_components():
    """Convert COMPONENT_NORMALIZATIONS to generic index definition format.

    Each component's `category` is remapped from its legacy name (the value
    stored in COMPONENT_NORMALIZATIONS) to its v1 name via
    SII_LEGACY_TO_V1_CATEGORY so the category labels match the 5 v1 categories
    declared in `SII_V1_DEFINITION["categories"]`. Legacy names that have no
    entry in the mapping fall through unchanged — fail visibly so a new
    legacy category added to COMPONENT_NORMALIZATIONS without a mapping
    surfaces as a missing category, not a silently dropped component.
    """
    components = {}
    for comp_id, spec in COMPONENT_NORMALIZATIONS.items():
        legacy_cat = spec["category"]
        components[comp_id] = {
            "name": comp_id.replace("_", " ").title(),
            "category": SII_LEGACY_TO_V1_CATEGORY.get(legacy_cat, legacy_cat),
            "legacy_category": legacy_cat,
            "weight": spec["weight"],
            "normalization": {
                "function": _fn_to_name(spec["fn"]),
                "params": spec["params"],
            },
            "data_source": "sii_collectors",
        }
    return components


SII_V1_DEFINITION = {
    "index_id": "sii",
    "version": "v1.1.0",
    "name": "Stablecoin Integrity Index",
    "description": "Deterministic, versioned scoring system for stablecoin risk",
    "entity_type": "stablecoin",
    "aggregation": {
        "formula": "coverage_weighted",
        "params": {"min_coverage": 0.0},
    },
    "categories": {
        cat_id: {"name": cat_id.replace("_", " ").title(), "weight": weight}
        for cat_id, weight in SII_V1_WEIGHTS.items()
    },
    # Legacy-only. Preserved on the definition for downstream readers
    # (methodology page, report renderers) that surfaced the structural
    # subcategory breakdown before v1.1.0. The weights here no longer
    # participate in overall SII computation; they're retained as the
    # reference for `legacy_sii_v1` and for the informational sub-scores
    # persisted to the `scores` table (reserves_score, contract_score,
    # oracle_score, governance_score, network_score).
    "structural_subcategories": {
        sub_id: {"name": sub_id.replace("_", " ").title(), "weight": weight}
        for sub_id, weight in STRUCTURAL_SUBWEIGHTS.items()
    },
    "components": _build_components(),
}
