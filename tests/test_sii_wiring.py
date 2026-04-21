"""
SII v1.1.0 wiring tests.

Four tests locking the methodology clarification shipped in this PR:

  a) Dispatch — aggregate() is invoked and the result carries the declared
     formula name and params.
  b) Divergence — legacy_renormalize vs coverage_weighted on a partially-
     populated synthetic SII fixture produce different overalls. If they
     agree, the formula migration is cosmetic.
  c) Category-activation — all 5 v1 categories land in category_scores
     when every component has a reading. Confirms the legacy→v1 remap
     inside app/index_definitions/sii_v1.py::_build_components works.
  d) Legacy reproducibility — the registry's `legacy_renormalize` formula
     is NOT byte-for-byte identical to the pre-wiring SII path
     (calculate_sii + aggregate_legacy_to_v1 + calculate_structural_composite)
     because the old path averaged components within legacy categories
     (ignoring COMPONENT_NORMALIZATIONS weights) whereas the registry
     formulas apply those weights. This test captures the delta with a
     ±0.05 tolerance so regressions surface loudly. See the PR description
     and docs/methodology/sii_changelog.md for the methodology rationale.

Plus an invariant check that the SII_LEGACY_TO_V1_CATEGORY mapping in the
definition agrees with LEGACY_TO_V1_MAPPING in app/scoring.py. Divergence
there would produce a silent category-assignment drift.
"""
from __future__ import annotations

import pytest

from app.composition import AGGREGATION_FORMULA_VERSION, aggregate
from app.index_definitions.sii_v1 import (
    SII_LEGACY_TO_V1_CATEGORY,
    SII_V1_DEFINITION,
)
from app.scoring import (
    COMPONENT_NORMALIZATIONS,
    LEGACY_TO_V1_MAPPING,
    SII_V1_WEIGHTS,
    aggregate_legacy_to_v1,
    calculate_sii,
)


# ---------------------------------------------------------------------------
# Synthetic fixture
# ---------------------------------------------------------------------------
# Real component_ids chosen to land in each legacy category (so the v1 remap
# activates every v1 category). Scores are deliberately heterogeneous so the
# coverage-weighted vs legacy-renormalize paths diverge.
#
# (component_id, legacy_category, normalized_score)
_FIXTURE = [
    # peg_stability (v1: peg_stability)
    ("peg_current_deviation", "peg_stability", 95.0),
    ("peg_7d_stddev",         "peg_stability", 90.0),
    # liquidity (v1: liquidity_depth)
    ("market_cap",            "liquidity",     85.0),
    ("volume_24h",            "liquidity",     80.0),
    # flows (v1: mint_burn_dynamics)
    ("daily_mint_volume",     "flows",         75.0),
    ("daily_burn_volume",     "flows",         70.0),
    # holder_distribution (v1: holder_distribution)
    ("top_10_concentration",  "holder_distribution", 65.0),
    ("unique_holders",        "holder_distribution", 60.0),
    # structural_risk_composite (5 legacy subcats):
    ("reserve_to_supply_ratio", "transparency",    90.0),  # transparency → structural
    ("contract_verified",     "smart_contract",   55.0),  # smart_contract → structural
    ("chain_count",           "network",          70.0),  # network → structural
    ("dao_timelock_hours",    "governance",       40.0),  # governance → structural
]


def _verify_fixture_exists():
    """Sanity: every fixture id must be in COMPONENT_NORMALIZATIONS and must
    carry the declared legacy category."""
    for comp_id, legacy_cat, _ in _FIXTURE:
        assert comp_id in COMPONENT_NORMALIZATIONS, f"unknown component {comp_id}"
        assert COMPONENT_NORMALIZATIONS[comp_id]["category"] == legacy_cat, (
            f"{comp_id} is in {COMPONENT_NORMALIZATIONS[comp_id]['category']}, "
            f"test fixture expects {legacy_cat}"
        )


def _fixture_component_scores():
    return {cid: score for cid, _, score in _FIXTURE}


def _fixture_raw_values():
    # Aggregation formulas consume component_scores; raw_values flow through
    # for downstream consumers. Supply 1.0 placeholders so no formula path
    # short-circuits on missing raw data.
    return {cid: 1.0 for cid, _, _ in _FIXTURE}


# ---------------------------------------------------------------------------
# Invariant: the two legacy→v1 mappings must agree
# ---------------------------------------------------------------------------


def test_legacy_and_v1_mappings_agree():
    """app/index_definitions/sii_v1.SII_LEGACY_TO_V1_CATEGORY mirrors
    app/scoring.LEGACY_TO_V1_MAPPING. Divergence would produce silent
    category-assignment drift between the legacy SII path and the registry
    path."""
    _verify_fixture_exists()
    # Every legacy cat referenced by COMPONENT_NORMALIZATIONS must map the
    # same v1 name through both tables.
    legacy_cats_in_use = {
        spec["category"] for spec in COMPONENT_NORMALIZATIONS.values()
    }
    for legacy_cat in legacy_cats_in_use:
        assert legacy_cat in SII_LEGACY_TO_V1_CATEGORY, (
            f"{legacy_cat} missing from SII_LEGACY_TO_V1_CATEGORY"
        )
        assert legacy_cat in LEGACY_TO_V1_MAPPING, (
            f"{legacy_cat} missing from scoring.LEGACY_TO_V1_MAPPING"
        )
        assert SII_LEGACY_TO_V1_CATEGORY[legacy_cat] == LEGACY_TO_V1_MAPPING[legacy_cat], (
            f"legacy_cat={legacy_cat}: definition says "
            f"{SII_LEGACY_TO_V1_CATEGORY[legacy_cat]}, scoring says "
            f"{LEGACY_TO_V1_MAPPING[legacy_cat]}"
        )


# ---------------------------------------------------------------------------
# Test a — Dispatch
# ---------------------------------------------------------------------------


def test_dispatch_emits_declared_formula_and_params():
    """aggregate() on SII_V1_DEFINITION returns the declared formula name
    and params on the result dict, confirming the declaration → dispatch
    plumbing is live."""
    cs = _fixture_component_scores()
    rv = _fixture_raw_values()
    result = aggregate(SII_V1_DEFINITION, cs, rv)
    assert result["method"] == "coverage_weighted"
    # params are declared on the definition and must land on the result.
    declared = SII_V1_DEFINITION["aggregation"]["params"]
    assert declared == {"min_coverage": 0.0}
    # formula_version is the registry's version string — stable across the PR.
    assert result["formula_version"] == AGGREGATION_FORMULA_VERSION
    # The aggregation envelope fields every downstream consumer depends on.
    for field in (
        "overall_score", "category_scores", "effective_category_weights",
        "coverage", "withheld", "method", "formula_version",
    ):
        assert field in result, f"aggregate() result missing {field}"
    assert result["withheld"] is False  # min_coverage=0.0 never withholds
    assert result["overall_score"] is not None


# ---------------------------------------------------------------------------
# Test b — Divergence
# ---------------------------------------------------------------------------


def test_legacy_renormalize_and_coverage_weighted_produce_different_overalls():
    """On a partially-populated fixture, legacy_renormalize and
    coverage_weighted must produce numerically different overalls. If they
    agree, the declared migration is cosmetic — coverage_weighted's
    effective-weight reweighting would have no effect and the report's
    Section B deltas wouldn't materialize."""
    cs = _fixture_component_scores()
    rv = _fixture_raw_values()

    legacy_def = dict(SII_V1_DEFINITION)
    legacy_def["aggregation"] = {"formula": "legacy_renormalize", "params": {}}
    legacy_result = aggregate(legacy_def, cs, rv)

    cw_def = dict(SII_V1_DEFINITION)
    cw_def["aggregation"] = {"formula": "coverage_weighted", "params": {"min_coverage": 0.0}}
    cw_result = aggregate(cw_def, cs, rv)

    legacy_overall = legacy_result["overall_score"]
    cw_overall = cw_result["overall_score"]
    assert legacy_overall is not None
    assert cw_overall is not None
    assert abs(legacy_overall - cw_overall) > 0.01, (
        f"legacy_renormalize={legacy_overall} vs coverage_weighted={cw_overall}; "
        f"formulas produced identical overalls — partial-category reweighting "
        f"has no effect on this fixture"
    )


# ---------------------------------------------------------------------------
# Test c — Category activation
# ---------------------------------------------------------------------------


def test_all_five_v1_categories_activate_when_fully_populated():
    """When every component in SII_V1_DEFINITION has a reading, all 5 v1
    categories populate in category_scores. Confirms the legacy→v1 remap
    inside _build_components works — without the remap, only peg_stability
    and holder_distribution would land (the two names that happen to
    overlap between the legacy and v1 vocabularies)."""
    cs = {cid: 80.0 for cid in SII_V1_DEFINITION["components"]}
    rv = {cid: 1.0 for cid in SII_V1_DEFINITION["components"]}
    result = aggregate(SII_V1_DEFINITION, cs, rv)
    expected_v1_cats = {
        "peg_stability", "liquidity_depth", "mint_burn_dynamics",
        "holder_distribution", "structural_risk_composite",
    }
    got_cats = set(result["category_scores"].keys())
    assert got_cats == expected_v1_cats, (
        f"expected {expected_v1_cats}, got {got_cats}"
    )
    # With all components at 80, the overall must be exactly 80.
    assert result["overall_score"] == 80.0


# ---------------------------------------------------------------------------
# Test d — Legacy reproducibility characterization
# ---------------------------------------------------------------------------


def test_registry_legacy_renormalize_differs_from_production_legacy_path():
    """The registry's legacy_renormalize is NOT byte-for-byte identical to
    the pre-wiring SII path (calculate_sii + aggregate_legacy_to_v1 +
    calculate_structural_composite) because the old path averaged
    components within legacy categories ignoring COMPONENT_NORMALIZATIONS
    weights, whereas the registry applies those weights. This is a
    characterization test — it locks the specific delta for the synthetic
    fixture so any regression surfaces loudly.

    This divergence is the methodology clarification stated in the SII
    v1.1.0 wiring PR: new scores use v1 categories directly with
    component-level weights; structural subcategory weights and the legacy
    three-level aggregation remain accessible only via the `legacy_sii_v1`
    formula slot for historical reproducibility.
    """
    cs = _fixture_component_scores()
    rv = _fixture_raw_values()

    # Path A: pre-wiring SII path — legacy-category simple averages + SII_V1_WEIGHTS
    legacy_cat_sums: dict[str, list[float]] = {}
    for comp_id, legacy_cat, score in _FIXTURE:
        legacy_cat_sums.setdefault(legacy_cat, []).append(score)
    legacy_avgs = {cat: sum(v) / len(v) for cat, v in legacy_cat_sums.items()}
    v1_scores = aggregate_legacy_to_v1(legacy_avgs)
    pre_wiring_overall = calculate_sii(v1_scores)

    # Path B: registry legacy_renormalize on SII_V1_DEFINITION
    legacy_def = dict(SII_V1_DEFINITION)
    legacy_def["aggregation"] = {"formula": "legacy_renormalize", "params": {}}
    registry_result = aggregate(legacy_def, cs, rv)
    registry_overall = registry_result["overall_score"]

    assert pre_wiring_overall is not None
    assert registry_overall is not None

    # Document the observed delta so a future refactor that accidentally
    # realigns the paths trips this test. If the paths ever converge, this
    # test should be updated alongside a deliberate methodology note.
    #
    # Observed on this fixture (12 components; 2 per v1 category except
    # structural which gets 4 across 4 legacy subcategories):
    #   pre-wiring (legacy-avg → aggregate_legacy_to_v1 → calculate_sii): 79.02
    #   registry legacy_renormalize (per-component weights inside v1 cats):  78.75
    #   delta = -0.27
    # The registry value is lower because structural's 4 populated legacy
    # subcategories average to a higher value under simple-average (55+70+40+90
    # → 63.75) than under the per-component-weight reweighting across the full
    # structural_risk_composite v1 category. Exact delta depends on
    # COMPONENT_NORMALIZATIONS weights; lock with a ±0.05 tolerance so a future
    # weights change that shifts it surfaces here.
    delta = registry_overall - pre_wiring_overall
    expected_delta = -0.27
    assert abs(delta - expected_delta) < 0.05, (
        f"pre_wiring={pre_wiring_overall}, registry={registry_overall}, "
        f"delta={delta:+.2f}, expected {expected_delta:+.2f}±0.05. "
        f"If the legacy path or COMPONENT_NORMALIZATIONS weights changed "
        f"intentionally, recalibrate this test and add a note to "
        f"docs/methodology/sii_changelog.md."
    )
