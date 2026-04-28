# Backfill Gaps — Honest Inventory

For every (entity, component, time period) with no source coverage, one line.

## Structural Gaps (cannot backfill)

| Index | Component | Entities Affected | Reason |
|-------|-----------|-------------------|--------|
| PSI | Smart contract analysis | All 13 | Blockscout source code only available for currently verified contracts; historical bytecode diffs not preserved |
| PSI | Component scores | All 13 | PSI formula requires live component collection; historical TVL alone is insufficient for full scoring |
| RPI | Protocol docs scoring | All 13 | Historical documentation snapshots not archived; only current docs are scoreable |
| RPI | Incident history | All 13 | Rekt database is editorial, not time-series; incidents are point-in-time events, not backfillable as scored components |
| BRI | Bridge volume | All bridges | DeFiLlama bridges API paywalled (V9.3); direct contract monitoring deferred to Phase 2 |
| CXRI | Reserve attestations | All 8 exchanges | Issuer PDFs are published periodically; historical PDFs not archived by Basis before CDA pipeline launch |
| TTI | NAV history | All 10 products | NAV is issuer-reported; historical values require issuer cooperation or web archive scraping |

## Partial Gaps (can backfill some components, not all)

| Index | Entity | Available | Missing | Source |
|-------|--------|-----------|---------|--------|
| PSI | All | TVL history (DeFiLlama) | Governance score, contract risk, oracle quality | Only TVL can be reconstructed; other components require live monitoring data |
| RPI | All | Governance proposal history (Snapshot) | Parameter change history, doc scores | Snapshot archives proposals; on-chain parameter reads require block-by-block replay |
| LSTI | steth, reth, cbeth | Price history (CoinGecko), supply (Blockscout) | Validator performance, slashing history | CoinGecko has 1y price; validator-level data requires archive node |
| DOHI | All DAOs | Proposal counts (Snapshot) | Vote quality, contributor diversity | Snapshot has proposal metadata; contributor analysis requires NLP on proposal bodies |

## Solana-Specific Gaps

| Entity | Component | Gap Reason |
|--------|-----------|------------|
| drift | All historical | Helius API key required; if not set, Solana backfill disabled entirely |
| jupiter-perpetual-exchange | All historical | Same as drift |
| raydium | All historical | Same as drift |

## Timeline Gaps

| Index | Entities | Earliest Possible Date | Reason |
|-------|----------|----------------------|--------|
| SII | All 36 stablecoins | ~2024-01-01 | CoinGecko API returns max 1 year of daily data on Analyst plan |
| PSI | aave, compound | Protocol deployment (~2020) | DeFiLlama has TVL since protocol launch |
| PSI | morpho, spark | ~2023 | Morpho Blue launched late 2023; Spark launched mid-2023 |
| Circle 7 | All | ~2025 | Indices only defined in V8.5+ (late 2025); no prior scoring methodology existed |

## What This Means

Backfilled rows have `backfilled=TRUE` and `backfill_source` indicating the data origin.
Many backfilled rows will have `overall_score=NULL` — meaning we have the TVL or price
data point but couldn't reconstruct the full multi-component score. These rows establish
the temporal skeleton; full historical scoring requires component-level reconstruction
which is a separate effort from this backfill.
