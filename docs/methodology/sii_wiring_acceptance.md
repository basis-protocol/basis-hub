# SII v1.1.0 Wiring — Acceptance Runbook

**Frozen-as-of:** commit `26101b7` (SII v1.1.0 declaration)
**Applies to:** the first post-deploy scoring cycle after the wiring PR lands
**Tolerance rule:** ±0.10 per entity. Exceedances are discrepancy reports,
not rollback triggers. The first post-deploy cycle's values are the new
ground truth; the table below is a prediction from yesterday's readings.

## Methodology clarification

Before this PR, SII computed overall via a three-level aggregation
(components → legacy categories simple-averaged → structural subcategories
simple-averaged → `STRUCTURAL_SUBWEIGHTS`-weighted composite → `SII_V1_WEIGHTS`-weighted
overall). The declaration on `SII_V1_DEFINITION` (v1.1.0, `coverage_weighted`
with `min_coverage=0.0`) did not take effect.

After this PR, SII computes overall via the registry's flat two-level
`aggregate()` path — components → v1 categories → overall, with
per-component weights from `COMPONENT_NORMALIZATIONS` applied inside each
v1 category, and `coverage_weighted` effective category weights driving the
overall sum. Structural subcategory scores (reserves_score / contract_score /
oracle_score / governance_score / network_score) are preserved on the
`scores` table as derived informational outputs; they no longer drive the
overall. The three-level path is preserved verbatim as the reference
implementation for the `legacy_sii_v1` formula slot so historical scores
remain reproducible.

`STRUCTURAL_SUBWEIGHTS` and `DB_TO_STRUCTURAL_MAPPING` are now legacy-only.

## Expected values — Section B, column cw@0.0

Frozen from `docs/methodology/aggregation_impact_analysis.md` §B as of
commit `26101b7`. 36 entities.

| entity | legacy | expected (cw@0.0) | delta |
|---|---|---|---|
| USDC | 93.36 | 94.60 | +1.24 |
| USDT | 89.44 | 90.44 | +1.00 |
| DAI | 84.52 | 85.77 | +1.25 |
| USD1 | 83.68 | 86.80 | +3.12 |
| USDS | 81.83 | 86.00 | +4.17 |
| PYUSD | 79.37 | 81.92 | +2.55 |
| RLUSD | 75.39 | 82.47 | +7.08 |
| crvUSD | 75.03 | 77.02 | +1.99 |
| GHO | 74.60 | 79.69 | +5.09 |
| FDUSD | 74.01 | 76.25 | +2.24 |
| USDe | 73.22 | 73.20 | -0.02 |
| TUSD | 72.85 | 75.89 | +3.04 |
| USDD | 71.52 | 75.45 | +3.93 |
| USDP | 70.44 | 79.01 | +8.57 |
| FRAX | 65.84 | 67.12 | +1.28 |
| MUSD | 64.77 | 74.87 | +10.10 |
| USDTB | 63.14 | 69.05 | +5.91 |
| DOLA | 63.11 | 69.06 | +5.95 |
| MIM | 60.33 | 68.36 | +8.03 |
| GUSD | 58.34 | 67.11 | +8.77 |
| OUSD | 56.99 | 64.01 | +7.02 |
| LUSD | 56.28 | 60.09 | +3.81 |
| EURC | 55.84 | 54.63 | -1.21 |
| SUSDS | 54.78 | 53.66 | -1.12 |
| SUSDE | 52.93 | 49.53 | -3.40 |
| EURI | 46.98 | 48.23 | +1.25 |
| STKGHO | 45.99 | 48.88 | +2.89 |
| STEAKUSDC | 42.52 | 40.76 | -1.76 |
| EURE | 42.33 | 43.54 | +1.21 |
| BUSD0 | 42.11 | 41.63 | -0.48 |
| sUSD | 38.09 | 36.49 | -1.60 |
| SDOLA | 37.71 | 38.23 | +0.52 |
| FRAX (variant) | 37.02 | 34.05 | -2.97 |
| RAI | 35.58 | 32.87 | -2.71 |
| USDD (BTTC bridge) | 35.20 | 33.68 | -1.52 |
| EURS | 33.09 | 24.92 | -8.17 |

Source: `docs/methodology/aggregation_impact_analysis.md` §B (regenerated
from production component_readings on 2026-04-21 via
`python scripts/analyze_aggregation_impact.py`). These are predictions,
not targets.

## Post-deploy verification

Run once against the first scoring cycle that writes v1.1.0 rows.

### Pull current SII overalls

```sql
-- Latest overall_score per stablecoin, with the aggregation envelope
-- v1.1.0 writes. aggregation_method='coverage_weighted' is the signal that
-- the wiring is live; rows written pre-wiring will show NULL.
SELECT
    st.symbol,
    s.overall_score,
    s.aggregation_method,
    s.aggregation_formula_version,
    s.coverage,
    s.withheld,
    s.computed_at
FROM scores s
JOIN stablecoins st ON st.id = s.stablecoin_id
ORDER BY s.overall_score DESC;
```

### Compare to this table

For each entity in the table above, compute `|new_overall - expected| ≤ 0.10`.

- **Pass:** all entities within ±0.10 of the expected value, and every row has
  `aggregation_method = 'coverage_weighted'` with `coverage` and
  `effective_category_weights` populated.
- **Discrepancy report (not rollback):** any entity outside ±0.10. Record
  the entity, the expected value, and the actual value. Likely causes:
  - Component readings drifted between report generation and first post-deploy
    cycle (prices/volumes/etc. update hourly — expected drift for some entities).
  - A new component landed in `COMPONENT_NORMALIZATIONS` between commits
    `26101b7` and the wiring PR — re-run the analyzer and refresh this table.
  - Collector produced a new value for a component that was missing at
    report time — legitimate new signal, not a regression.
- **Rollback trigger:** `aggregation_method IS NULL` on any v1.1.0-cycle row,
  or `overall_score` systematically regresses toward pre-wiring values for
  all entities. That indicates the dispatch isn't active.

### Spot-check the canonical anchor

```sql
SELECT overall_score, aggregation_method, coverage, withheld
FROM scores WHERE stablecoin_id = 'usdc';
-- Expect: overall_score ≈ 94.60, aggregation_method = 'coverage_weighted',
-- coverage ~ 0.62, withheld = false.
```

## Follow-ups not in this PR

- CQI/RQS re-attestation: SII inputs now reflect coverage_weighted aggregation.
  Any CQI pair or RQS snapshot computed before this PR lands is still
  correct under its own timestamp, but downstream re-attestation will be
  needed when CQI/RQS consumers want to reflect the new SII basis.
  Tracked as `basis-hub#cqi-rqs-reattestation`.
- Backfilling historical `scores` rows with aggregation envelope fields:
  NOT to be done. V9.9 preserves historical scores at their original
  formula name and methodology version. Pre-wiring rows stay NULL.
