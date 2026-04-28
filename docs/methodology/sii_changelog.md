# SII Methodology Changelog

## v1.1.0 — 2026-04-21 (wiring landed)

**Status as of the wiring PR on `claude/sii-dispatch-wiring`:** production SII
scoring is now routed through `app.composition.aggregate()` with the
declared formula (`coverage_weighted`, `min_coverage=0.0`). The declaration
and dispatch match.

Methodology clarification: SII flattened from three-level aggregation
(components → legacy categories → structural subcategories → v1 categories →
overall) to two-level (components → v1 categories → overall). Structural
subcategory weights (`STRUCTURAL_SUBWEIGHTS`) and the legacy→v1 category
remap (`DB_TO_STRUCTURAL_MAPPING` / `LEGACY_TO_V1_MAPPING`) are preserved
for historical reproducibility under the `legacy_sii_v1` formula slot but
no longer participate in current scoring. New SII scores use the v1
category structure directly with component-level weights from
`COMPONENT_NORMALIZATIONS`. Expected movement: USDC 93.36 → 94.60 per
Section B of `docs/methodology/aggregation_impact_analysis.md`; full
Section B table frozen in `docs/methodology/sii_wiring_acceptance.md`.

The 5 structural subcategory scores (reserves_score, contract_score,
oracle_score, governance_score, network_score) continue to be computed
from the legacy per-category averages and persisted to the `scores` table
as derived informational outputs. They no longer drive the overall.

Code changes:
- `app/index_definitions/sii_v1.py` — `SII_LEGACY_TO_V1_CATEGORY` added;
  `_build_components` now remaps component categories to v1 names.
- `app/worker.py::compute_sii_from_components` — dispatches via
  `aggregate(SII_V1_DEFINITION, component_scores, raw_values)`; structural
  sub-scores preserved as informational.
- `app/worker.py::store_score` — persists the six aggregation envelope
  fields (columns already added by migration 084).
- `app/server.py` — `/api/scores`, `/api/scores/{coin}`, and `/api/indices`
  emit aggregation fields.
- `scripts/analyze_aggregation_impact.py` — analyzer's local SII category
  remap removed; imports from the shared definition.
- `tests/test_sii_wiring.py` — four tests locking dispatch, divergence,
  category-activation, and legacy-path divergence.

No new migration. Migration 084 already added the aggregation envelope
columns to the `scores` table.

## v1.1.0 — 2026-04-21 (declaration only)

**Aggregation migration:** `legacy_renormalize` → `coverage_weighted` with `min_coverage=0.0`.

- Declared via `SII_V1_DEFINITION.aggregation` in `app/index_definitions/sii_v1.py`.
- Weights, categories, and components unchanged.
- Justification: `docs/methodology/aggregation_impact_analysis.md` (Section B — SII). Under coverage-weighted, categories contribute to the overall in proportion to their populated-weight fraction, so partially-populated categories are no longer silently over-weighted relative to fully-populated peers. Net shift for the USDC anchor is +~1 point (93.36 → ~94.60 per Section B of the report).
- **Production scoring path wiring deferred.** `app/scoring.py::calculate_sii` and `app/worker.py::compute_sii_from_components` did not yet dispatch through `app.composition.aggregate` at the time of this entry; that wiring landed in the subsequent entry above.

## v1.0.0 — 2025-12-28

Initial public release. Formula: `SII = 0.30·Peg + 0.25·Liquidity + 0.15·MintBurn + 0.10·Distribution + 0.20·Structural`.
