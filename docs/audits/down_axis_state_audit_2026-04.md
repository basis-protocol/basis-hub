# Down-Axis State Audit — April 2026

**Audit date:** 2026-04-24
**Scope:** Every historical, unreplicable, risk-relevant state series Basis should be collecting
**Output:** Ranked backlog of collectors to start, schema work to sequence, and gaps to defer with documentation
**Method:** Direct inspection of `/home/user/basis-hub` — collector files, `app/enrichment_worker.py` registration, worker/background-loop wiring in `app/worker.py` and `main.py`, and migrations 001–098

---

## Preamble — Register of Honesty

Every verdict in this document is grounded in code I read. Where I did not find evidence, I say "no evidence found" rather than "does not exist." Three structural caveats apply throughout:

1. **The codebase is young.** Earliest collector first-commit date is **2026-04-13** (11 days before this audit). The "down axis" in its current form is ~2 weeks tall everywhere. Every verdict of "collecting today" therefore refers to *recent* collection, not long-horizon collection.
2. **Wired vs written is the load-bearing distinction.** A collector file existing in `app/collectors/` or `app/data_layer/` means very little. Only collectors invoked by `app/enrichment_worker.py::run_enrichment_pipeline` (slow cycle), `app/collectors/registry.py` (fast SII cycle), or an `asyncio.create_task` background loop in `app/worker.py::main()` are actually producing state. I call this distinction out explicitly in Section 1.
3. **My collector-surface sub-agent classified many slow-cycle collectors as "orphaned."** I have overridden that classification where I found them registered in `enrichment_worker.py`. The corrected wiring column in Section 1 is mine, not the agent's.

---

## Section 1 — Collector Surface Audit

### 1.1 Where collection actually happens

| Loop | Location | What runs here |
|---|---|---|
| **Fast cycle (hourly)** | `app/worker.py::run_scoring_cycle` via `app/collectors/registry.py` | SII components only — coingecko, defillama, curve, etherscan, flows, solana, smart_contract, actor_metrics, offline, derived |
| **Slow cycle (≈3h)** | `app/enrichment_worker.py::run_enrichment_pipeline` | Circle-7 scoring (LSTI/BRI/VSRI/CXRI/TTI/DOHI), RPI, DEX pools, governance proposals, treasury flows, liquidity, yield, exchange, mint/burn, CDA, wallet expansion, edges, peg 5-min, OHLCV, entity snapshots, wallet behavior, divergence, incident detection, PSI expansion, holder discovery, contract surveillance, correlation, materialised compositions |
| **Background loops** | `app/worker.py::main()` via `asyncio.create_task` | `mempool_watcher` (continuous WS), `trace_collector` (6h loop), `approval_collector` (daily loop), Phase-2 wallet-presence / multichain / SSS loops |
| **Main-thread lookback** | `main.py` startup block around line 331 | `bridge_flow_collector` is wired HERE but `enrichment_worker.py` explicitly comments `# Tier 4: Bridge flows — DEFERRED (constitution v9.3)`, so its actual runtime status is contested — see Section 2 Category H and the Step-5 honesty check |

### 1.2 Summary counts

| Class | Count | Source of count |
|---|---|---|
| Total collector files under `app/collectors/`, `app/data_layer/`, `app/rpi/`, `app/services/*_collector.py`, `app/ops/tools/*_monitor.py` | ≈ 55 | Direct `find` listing |
| Collectors wired into a scoring path | ≈ 45 | Cross-ref against `enrichment_worker.py` + `worker.py` + `registry.py` |
| Collectors **written but not wired** | 1 confirmed (`bridge_flow_collector`) | `enrichment_worker.py` line ≈ 640 comment |
| Migrations applied (0–098) | 98 (some duplicate numbers — 028/029/052/053/054/055/069/091) | `ls migrations/` |
| First-commit date range across all collector files | 2026-04-13 → 2026-04-22 | `git log --reverse --format=%ad` per file |

### 1.3 Collector inventory

Columns: **path** · **purpose** · **source** · **wired loop** · **write target** · **first commit**. "Attestation domain" is omitted from the row where my sub-agent found none — attestation coverage is summarised in the appendix to this section.

| Path | Purpose | Source | Wired | Write target | First commit |
|---|---|---|---|---|---|
| `app/collectors/coingecko.py` | Peg, liquidity, market cap, 5-min spot | CoinGecko Pro | FAST | `component_readings` | 2026-04-19 |
| `app/collectors/defillama.py` | TVL, protocol TVL, cross-chain liquidity | DeFiLlama free | FAST | `component_readings` | 2026-04-19 |
| `app/collectors/curve.py` | Curve pool depth / virtual price | Curve subgraph | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/etherscan.py` | Holder counts, distribution HHI | Etherscan V2 | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/flows.py` | Aggregate mint/burn derived from balance changes | RPC / subgraph | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/solana.py` | Solana-side supply + liquidity | Helius | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/smart_contract.py` | Governance reads, upgrade flags | RPC | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/actor_metrics.py` | Actor classification features | Internal | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/offline.py` | Static transparency/regulatory/governance/reserves | Static config | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/derived.py` | Derived components from FAST inputs | Computed | FAST | `component_readings` | 2026-04-13 |
| `app/collectors/psi_collector.py` | Protocol safety components + discovery | DeFiLlama, RPC | SLOW (psi_expansion + worker PSI loop) | `psi_scores`, `psi_components`, `protocol_backlog`, `protocol_collateral_exposure` | 2026-04-19 |
| `app/collectors/lst_collector.py` | LSTI components | DeFiLlama + static + Rated | SLOW (`lsti_scoring`) | `generic_index_scores` (lsti) | 2026-04-19 |
| `app/collectors/bridge_collector.py` | BRI components | DeFiLlama TVL + static | SLOW (`bri_scoring`) | `generic_index_scores` (bri) | 2026-04-13 |
| `app/collectors/bridge_monitors.py` | Bridge message-passing health probes | Custom | SLOW (bri_scoring helper) | bri components | 2026-04-13 |
| `app/collectors/vault_collector.py` | VSRI components | DeFiLlama yields + static | SLOW (`vsri_scoring`) | `generic_index_scores` (vsri) | 2026-04-13 |
| `app/collectors/cex_collector.py` | CXRI components | CoinGecko exchange + static | SLOW (`cxri_scoring`) | `generic_index_scores` (cxri) | 2026-04-13 |
| `app/collectors/tti_collector.py` | TTI components | Static + issuer sources | SLOW (`tti_scoring`) | `generic_index_scores` (tti) | 2026-04-13 |
| `app/collectors/dao_collector.py` | DOHI components | Snapshot/Tally + static | SLOW (`dohi_scoring`, gated 24h) | `generic_index_scores` (dohi) | 2026-04-13 |
| `app/collectors/dex_pools.py` | DEX pool inventory | DeFiLlama + GeckoTerminal | SLOW (`dex_pool_collection`, 3h gate) | `generic_index_scores` (dex_pool_data) | 2026-04-13 |
| `app/collectors/governance_events.py` | Governance activity delta | Snapshot + Tally | SLOW (`governance_events`) | `governance_events` | 2026-04-13 |
| `app/collectors/governance_proposals.py` | Canonical proposal corpus | Snapshot + Tally GraphQL | SLOW (via `data_layer/governance_collector`, 24h gate) | `governance_proposals`, `governance_proposal_snapshots` | 2026-04-19 |
| `app/collectors/governance_detector.py` | Governance config drift | RPC | FAST | `psi_governance_snapshots`, `score_events` | 2026-04-13 |
| `app/collectors/treasury_flows.py` | Labelled-treasury behavioural events | RPC + `treasury_registry` | SLOW (`treasury_flows`) | `wallet_graph.treasury_events` | 2026-04-13 |
| `app/collectors/oracle_behavior.py` | Per-reading price + deviation + latency | RPC + CEX compare | SLOW (via `worker.py:1576`) | `oracle_price_readings`, `oracle_stress_events` | 2026-04-19 |
| `app/collectors/parameter_history.py` | On-chain governance parameter changes | RPC event logs | SLOW (via worker) | `protocol_parameter_changes`, `protocol_parameters`, `protocol_parameter_snapshots` | 2026-04-19 |
| `app/collectors/contract_upgrades.py` | Upgrade-proxy delta events | RPC | SLOW | `contract_upgrade_history`, `contract_bytecode_snapshots` | 2026-04-14 |
| `app/collectors/contract_dependencies.py` | Dependency-graph snapshots | Sourcify + RPC | SLOW | `contract_dependencies`, `dependency_graph_snapshots` | 2026-04-19 |
| `app/collectors/clustered_concentration.py` | Graph-clustered holder concentration | Wallet graph | SLOW | `concentration_snapshots`, `holder_clusters` | 2026-04-19 |
| `app/collectors/morpho_blue.py` | Morpho market inventory | Morpho subgraph | SLOW | `morpho_markets`, `protocol_collateral_exposure` | 2026-04-19 |
| `app/collectors/on_chain_cda.py` | On-chain CDA verification | RPC | SLOW | `cda_vendor_extractions` | 2026-04-19 |
| `app/collectors/pool_wallet_collector.py` | Receipt-token → wallet mapping | Blockscout + Etherscan | SLOW (24h gate) | `protocol_pool_wallets`, `wallet_graph.wallets` | 2026-04-13 |
| `app/collectors/holder_analysis.py` | Per-asset holder distribution | Etherscan | SLOW (used by FAST components) | none direct | 2026-04-13 |
| `app/collectors/rated_validators.py` | Validator attestation/slashing signal | Rated Network | SLOW (LSTI feeder, gap-covered) | `validator_performance_snapshots` | 2026-04-14 |
| `app/collectors/enforcement_history.py` | CourtListener + SEC EDGAR | External | SLOW (CXRI/TTI feeder) | `enforcement_records` | 2026-04-14 |
| `app/collectors/parent_company_financials.py` | SEC EDGAR XBRL pulls | SEC EDGAR | SLOW | `parent_company_financials` | 2026-04-14 |
| `app/collectors/sanctions_screening.py` | OpenSanctions screens | OpenSanctions | SLOW | `sanctions_screening_results` | 2026-04-14 |
| `app/collectors/static_evidence.py` | Evidence store for manual checks | Internal | SLOW | `static_evidence` | 2026-04-13 |
| `app/collectors/regulatory_scraper.py` | Reg-registry lookups | Firecrawl | SLOW | `regulatory_registry_checks` | 2026-04-19 |
| `app/collectors/solana_program_monitor.py` | Solana program upgrade watch | Helius | FAST/SLOW | `contract_surveillance`, `contract_upgrade_history` | 2026-04-19 |
| `app/collectors/exchange_health.py` | Exchange-API health ping | Exchange APIs | SLOW | `exchange_health_checks` | 2026-04-13 |
| `app/collectors/web_research.py` | Parallel.ai web research | Parallel.ai | SLOW (24h gate) | `generic_index_scores` (web_research_*) | 2026-04-13 |
| `app/collectors/collateral_coverage.py` | Market-cap / velocity snapshots | CoinGecko | SLOW | `protocol_market_snapshots` | 2026-04-13 |
| `app/data_layer/mint_burn_collector.py` | Per-event mint/burn capture | Etherscan V2 `tokentx` | SLOW (`mint_burn_events`, 24h gate) | `mint_burn_events`, `discovery_signals` | 2026-04-13 |
| `app/data_layer/liquidity_collector.py` | Per-asset liquidity depth | DEX subgraphs | SLOW (`liquidity_depth`, no gate) | `liquidity_depth` | 2026-04-13 |
| `app/data_layer/yield_collector.py` | Yield pool snapshots | DeFiLlama yields | SLOW (24h gate) | `yield_snapshots` | 2026-04-13 |
| `app/data_layer/markets_collector.py` | Bulk markets + 5-min pulls | CoinGecko | SLOW | `market_chart_history`, `entity_snapshots_hourly` | 2026-04-13 |
| `app/data_layer/peg_monitor.py` | 5-min peg + volatility | CoinGecko | SLOW (20h gate) | `peg_snapshots_5m` | 2026-04-19 |
| `app/data_layer/ohlcv_collector.py` | Pool-level OHLCV | GeckoTerminal | SLOW (3h gate) | `dex_pool_ohlcv` | 2026-04-13 |
| `app/data_layer/market_chart_backfill.py` | 90-day market backfill | CoinGecko | SLOW (20h gate) | `market_chart_history` | 2026-04-19 |
| `app/data_layer/correlation_engine.py` | Correlation matrices | Computed | SLOW (24h gate) | `correlation_matrices` | 2026-04-13 |
| `app/data_layer/exchange_collector.py` | Exchange reserves + trust | CoinGecko | SLOW (1h gate) | `exchange_snapshots` | 2026-04-13 |
| `app/data_layer/governance_collector.py` | Full Snapshot/Tally proposal corpus | GraphQL | SLOW (24h gate) | `governance_proposals` + votes JSONB | 2026-04-13 |
| `app/data_layer/entity_snapshots.py` | Hourly entity snapshots | CoinGecko + DeFiLlama | SLOW (1h gate) | `entity_snapshots_hourly` | 2026-04-19 |
| `app/data_layer/wallet_behavior.py` | Behavioural wallet tagging | Computed | SLOW (24h gate) | `wallet_behavior_tags` | 2026-04-19 |
| `app/data_layer/holder_discovery.py` | Deep paginated holder discovery | Blockscout | SLOW (24h gate) | `wallet_graph.wallets` | 2026-04-13 |
| `app/data_layer/holder_ingestion_collector.py` | Holder ingest for Phase 2 | Etherscan | BACKGROUND LOOP | `wallet_holder_discovery` | 2026-04-22 |
| `app/data_layer/multichain_holder_collector.py` | Multi-chain holder presence | Blockscout | BACKGROUND LOOP | `wallet_graph.wallets`, `wallet_chain_presence` | 2026-04-22 |
| `app/data_layer/wallet_presence_scanner.py` | Chain presence verify | Blockscout | BACKGROUND LOOP | `wallet_chain_presence` | 2026-04-22 |
| `app/data_layer/trace_collector.py` | Protocol tx trace observations (Pipeline 1) | Blockscout raw-trace | BACKGROUND LOOP (6h) | `protocol_trace_observations` | 2026-04-22 |
| `app/data_layer/approval_collector.py` | ERC-20 approval diffs (Pipeline 2) | RPC `Approval` logs | BACKGROUND LOOP (24h) | `token_approval_snapshots` | 2026-04-22 |
| `app/data_layer/oracle_cadence_collector.py` | Chainlink round updates + gaps | RPC | SLOW | `oracle_update_cadence` | 2026-04-22 |
| `app/data_layer/mempool_watcher.py` | Pending-tx capture for watchlist | Alchemy WS | BACKGROUND LOOP (continuous) | `mempool_observations` | 2026-04-22 |
| `app/data_layer/contract_surveillance.py` | Contract upgrade surveillance | RPC | SLOW (weekly gate) | `contract_surveillance` | 2026-04-19 |
| `app/data_layer/wallet_expansion.py` | Wallet-graph growth | Seed lists + Etherscan | SLOW (no gate) + growth (24h gate) | `wallet_graph.wallets` | 2026-04-19 |
| `app/data_layer/entity_discovery.py` | Weekly entity discovery | Computed | SLOW (weekly gate) | `discovery_signals` | 2026-04-13 |
| `app/data_layer/incident_detector.py` | Auto-incident detection | Computed | SLOW (12h gate) | `incident_events` | 2026-04-19 |
| `app/data_layer/materialized_compositions.py` | Materialised CQI / RQS views | Computed | SLOW | `composed_scores_*` | 2026-04-13 |
| `app/data_layer/bridge_flow_collector.py` | Directional bridge flows | DeFiLlama `/bridges` | **NOT WIRED in SLOW — DEFERRED v9.3** (main.py startup block only, may be stale) | `bridge_flows` | 2026-04-13 |
| `app/data_layer/index_simulator.py` | Component-replay back-tests | Computed | SLOW | `index_simulations` | 2026-04-19 |
| `app/rpi/snapshot_collector.py` | RPI Snapshot proposal pulls | Snapshot | SLOW (via `rpi_scoring`) | `governance_proposals` | 2026-04-13 |
| `app/rpi/tally_collector.py` | RPI Tally proposal pulls | Tally | SLOW (via `rpi_scoring`) | `governance_proposals` | 2026-04-13 |
| `app/rpi/parameter_collector.py` | RPI parameter changes | RPC events | SLOW (via `rpi_scoring`) | `parameter_changes` | 2026-04-13 |
| `app/rpi/forum_scraper.py` | DAO forum scrape | Firecrawl | SLOW (via `rpi_scoring`) | `governance_forum_posts` | 2026-04-13 |
| `app/rpi/docs_scorer.py` | Docs scoring | Static eval | SLOW (via `rpi_scoring`) | `rpi_doc_scores` | 2026-04-13 |
| `app/rpi/incident_detector.py` | RPI incident detection | Computed | SLOW (via `rpi_scoring`) | `incident_events` | 2026-04-13 |
| `app/rpi/revenue_collector.py` | Annualised revenue via DeFiLlama fees | DeFiLlama `/summary/fees` | SLOW (via `rpi_scoring`) | consumed into `rpi_components` | 2026-04-13 |
| `app/services/cda_collector.py` | CDA waterfall (Extract/Search/Firecrawl/Reducto) | Adaptive vendor | SLOW (24h gate) | `cda_vendor_extractions`, `cda_issuer_registry`, `cda_monitors` | 2026-04-13 |
| `app/services/tti_disclosure_collector.py` | TTI issuer disclosure parsing | Firecrawl + Reducto | SLOW | `tti_disclosure_extractions` | 2026-04-19 |
| `app/services/contagion_archive.py` | Divergence → contagion archive | Computed from divergence | SLOW (via divergence step) | `contagion_events` | 2026-04-14 |
| `app/ops/tools/governance_monitor.py` | Ops governance surface | Snapshot/Tally | Ops loop | `ops_governance_proposals`, `ops_target_content` | 2026-04-13 |
| `app/ops/tools/oracle_monitor.py` | Ops oracle surface | Oracle tables | Ops loop | `oracle_external_interactions`, `keeper_publish_log` | 2026-04-13 |
| `app/ops/tools/keeper_monitor.py` | Keeper balance/gas telemetry | Keeper RPC | Ops loop | (memory / logs) | 2026-04-13 |
| `app/ops/tools/news_monitor.py` | News surface | CoinGecko news | Ops loop | `ops_coingecko_news` | 2026-04-13 |
| `app/ops/tools/twitter_monitor.py` | Twitter content surveillance | Parallel Search | Ops loop | `ops_target_content` | 2026-04-13 |
| `app/ops/tools/investor_monitor.py` | Investor content surveillance | Firecrawl | Ops loop | `ops_investor_content` | 2026-04-13 |
| `app/ops/tools/scraper.py` | Generic content scraper | Parallel Extract | Ops loop | `ops_target_content` | 2026-04-13 |

### 1.4 Appendix — collector/domain orphans

> **CORRECTION (2026-04-24, post-publication).** This appendix originally claimed 14 attestation domains were "declared but with no collector writing to them." That claim was **wrong** — it propagated a classification error from a sub-agent that did not grep for `attest_state(...)` call sites. Subsequent investigation (triggered by ENG-TICKET review) confirmed all 14 domains have active call sites. The corrected analysis appears below; the original false claim is preserved in struck-through form for traceability.

#### Original (incorrect) claim — STRUCK THROUGH

> ~~**Attestation domains declared but with no collector writing to them:**~~
> ~~`actors`, `cqi_compositions`, `discovery_signals`, `divergence_signals`, `edges`, `provenance`, `psi_components`, `psi_discoveries`, `rpi_components`, `rqs_composition`/`rqs_compositions`, `sii_components`, `wallet_profiles`, `wallets` (14 total).~~

#### Corrected analysis

**All 14 domains are wired.** Confirmed via `grep -rnE "attest_state\(" app/`:

| Domain | Call site | Hashed payload |
|---|---|---|
| `sii_components` | `app/worker.py:599` | `[{component_id, normalized_score}]` per stablecoin — **genuine component-level** |
| `psi_components` | `app/worker.py:981` | `[{slug, overall_score}]` — **summary only, not components** |
| `rpi_components` | `app/worker.py:1749` | `[{slug, overall_score}]` — **summary only, not components** |
| `actors` | `app/actor_classification.py:384` | classification counts |
| `cqi_compositions` | `app/composition.py:446` | `[{asset, protocol, cqi_score}]` |
| `rqs_composition` | `app/composition.py:356` | composition payload |
| `rqs_compositions` | `app/composition.py:385` | composition payload |
| `discovery_signals` | `app/discovery.py:229` | signal type + novelty |
| `divergence_signals` | `app/worker.py:2217` | divergence summary |
| `provenance` | `app/worker.py:2342` | provenance rows |
| `psi_discoveries` | `app/worker.py:2382` | discovery counters |
| `edges` | `app/indexer/edges.py:327` | per-chain edge counts |
| `wallet_profiles` | `app/indexer/profiles.py:194` | profile build counters |
| `wallets` | `app/indexer/pipeline.py:786` | wallet batch counters |

**The real gap that surfaced from this re-investigation** (relevant to anyone reading this section to scope attestation work):

1. **`psi_components` and `rpi_components` attest summaries, not components.** Domain names are misleading. Either the names should be changed (e.g. `psi_score_summaries`) or the payloads should expand to per-component arrays matching the `sii_components` pattern.
2. **`rpi_components` is missing from the daily state root** — the `ATTESTATION_DOMAINS` list at `app/pulse_generator.py:247-255` includes 21 domains but omits `rpi_components`. One-line fix.
3. **`/api/attestation/{domain}/latest` and `/api/attestation/{domain}/history` endpoints do not exist** — only `/api/state-root/latest`. Adding them is a small new-code task if external verifiers are expected to consume per-domain attestation.
4. **No per-row `content_hash` + `attested_at` columns on `component_readings`, `psi_components`, `rpi_components`** — this is a different attestation philosophy from the `oracle_price_readings` per-row pattern. Whether to adopt it is a design decision, not a fix.

**FAST-cycle collectors writing without a declared attestation domain — actually fine.** The original appendix claimed `coingecko`/`defillama`/`curve`/`etherscan`/`solana`/`actor_metrics`/`flows`/`offline`/`derived` write `component_readings` rows without attestation. Technically true at the producer level, but the **integration boundary is attested** at `worker.py:599` via `sii_components`, hashing all ~102 normalized scores per stablecoin. Per-collector attestation would multiply hash count without adding verifiability. Treat the original framing as overstated.

**Written-but-not-wired:** Only `app/data_layer/bridge_flow_collector.py` is confirmed dead by the explicit `# DEFERRED (constitution v9.3)` comment at `app/enrichment_worker.py`. All other collectors my sub-agent flagged as "orphaned" are in fact wired through the SLOW cycle or background loops — corrected in Section 1.3 above.

---

## Section 2 — Category-by-Category Gap Assessment

Each verdict is **NOT COLLECTING / PARTIAL / COLLECTING** with the concrete evidence used to reach it.

### Category A — Strategy / structured-position state

**Verdict: NOT COLLECTING.**

**Evidence:**
- Grep for `lending_position`, `borrow_position`, `position_entity`, `strategy_entity` across `app/` and `migrations/` returns **zero hits**.
- The schema has `protocol_pool_wallets` (`migrations/055_protocol_pool_wallets.sql`) — this records *which wallet holds a receipt token*, not *what the position parameters are*. A wallet holding `aUSDC` is captured; the LTV it's sitting at, the borrow side of the position, the liquidation threshold at current collateral — none of this is captured.
- `app/collectors/protocol_adapters.py:390` registers `PT-sUSDe (Pendle Principal Token)` as a receipt-token type `pt_token`, but the entry is a static mapping of token → underlying. There is no series for "at time T, X sUSDe is locked in a Pendle PT expiring date D." If the PT expires, the entry remains in the static registry but the *expiring series* is lost.
- `app/collectors/morpho_blue.py` populates `morpho_markets` and `protocol_collateral_exposure`, i.e. the *protocol-level* TVL in Morpho markets — not per-position state.
- No Aave / Compound / Morpho **per-position** collector exists. `app/collectors/psi_collector.py` treats Aave as one entity with aggregate metrics.

**The gap is canonical — the down-axis entity is the *position*, not the *token* — and this entity class does not exist in the schema.**

### Category B — Liquidation cascade thresholds

**Verdict: NOT COLLECTING.**

**Evidence:**
- Grep for `liquidation_curve`, `liquidation_cascade`, `cascade_scenario` across `app/` and `migrations/` returns **zero hits**. `liquidation_threshold` appears only as a static `parameter_name` in `app/collectors/parameter_history.py:127` (protocol-parameter tracking), not a computed curve.
- `app/divergence.py` + `app/services/contagion_archive.py` + `migrations/063_contagion_event_archive.sql` write a `contagion_events` table with `propagation_summary JSONB` and `affected_entities JSONB`. This captures *reachability* in the wallet graph once a trigger has fired, not a *pre-trigger price → liquidatable-notional* curve.
- `app/playground.py:114::compute_stress_scenarios` runs client-side stress scenarios on a user-supplied portfolio (fixed shock %) — this is interactive and ephemeral; nothing is persisted as down-axis state.

**Closest adjacent state that exists:** `protocol_parameter_snapshots` (static LTV/liq-threshold params) and `protocol_pool_wallets` (who holds receipts). The *product* of these two with current price and per-market debt would yield a liquidation curve, but this product is neither computed nor stored.

### Category C — Parameter-change downstream effects

**Verdict: PARTIAL.**

**Evidence:**
- `migrations/071_protocol_parameter_history.sql` captures `protocol_parameter_changes` with columns `concurrent_sii_score`, `concurrent_psi_score`, `hours_since_last_sii_change`, `sii_trend_7d`, `change_context`. This is a *concurrent-score* snapshot at change time — not a before/after *metric* window.
- No table joins `protocol_parameter_changes` × time-windowed TVL, utilisation, liquidation volume, or new-position opens. Grep for `parameter_change.*join|before.*after.*param` returns no such precomputed artifact.
- The raw ingredients exist: `protocol_parameter_changes.changed_at`, `entity_snapshots_hourly`, `liquidity_depth`, `yield_snapshots`, `mint_burn_events` (for stables). A 24/48/72h window join is a query, not a new collector.

**This is mostly a rendering / aggregation problem, not a collection problem.** Flagged explicitly per Step 5 §5.

### Category D — Cross-venue redemption friction for stablecoins

**Verdict: NOT COLLECTING.**

**Evidence:**
- Grep for `issuer_redemption`, `redemption_volume`, `circle_mint`, `paxos_mint`, `issuer_settlement` returns **zero hits**.
- `app/data_layer/mint_burn_collector.py` captures zero-address Transfer events, which conflates (a) issuer mint/redeem with (b) any protocol burn/mint. There is no tag separating "Circle wallet minted to Treasury A" from a Morpho share burn. The docstring at line 10 advertises "Redemption acceleration: 14 burns >$1M in last 6h" — this is bulk burn, not issuer-direct redemption.
- There is no separate series for **issuer settlement latency** (time from burn event to off-chain USD settlement). This is by nature not on-chain, but also not being sampled from Circle / Paxos API.
- SII's cross-exchange variance is computed from `cex_price` at the oracle layer (`oracle_price_readings.cex_price`) — price variance, not redemption variance.

### Category E — Delegate voting power by proposal type

**Verdict: PARTIAL.**

**Evidence:**
- `migrations/069_governance_proposals.sql` captures `governance_proposals` with `votes JSONB`, `choices JSONB`, and `body`, `title`. The vote-by-vote detail is there as JSONB.
- `migrations/052_rpi_tables.sql` has a *separate* `governance_proposals` table (different schema — same name, distinct from 069's) that includes `is_risk_related BOOLEAN` and `risk_keywords TEXT[]`. This is a binary classifier, not a multi-class one (risk / treasury / integration / misc).
- There is no delegate-address → proposal-type time series. Grep for `delegate_registry`, `voter_history`, `vote_by_proposal` returns nothing. The only match is `app/collectors/dao_collector.py:205` which records `delegate_count` as a scalar, not a per-delegate history.
- The Mantle-Aave 130K-AAVE delegated power angle cannot be answered from stored state today: we know *who voted what on which proposal* (raw JSONB), but there is no "which delegates vote on risk-parameter proposals for Aave historically" indexed view.

**Closest adjacent state:** vote-level JSONB is there; the proposal-type classification and the per-delegate longitudinal series are not. Mostly schema + classification work, not a new collector.

### Category F — Insurance-fund depletion rate

**Verdict: NOT COLLECTING.**

**Evidence:**
- Grep for `insurance_fund`, `safety_module`, `stability_pool`, `reserve_fund` across `app/` and `migrations/` returns **zero hits**. `aave_safety` / `aave_reserve`: zero hits.
- Revenue *is* captured via `app/rpi/revenue_collector.py` → DeFiLlama `/summary/fees/{slug}` → annualised figure consumed into `rpi_components`. This is a scalar per cycle, not a persisted balance series.
- The insurance-fund balance itself is an on-chain balanceOf of known contracts (Aave Safety Module = stkAAVE staking contract, Morpho insurance contract, etc.). Collecting it is a thin RPC adapter. Today: not done.
- Ratio (depletion rate / revenue accrual) is not computed anywhere.

### Category G — MEV extraction during stablecoin stress

**Verdict: NOT COLLECTING.**

**Evidence:**
- Grep for `flashbot`, `eigenphi`, `libmev`, `mev_inspect`, `sandwich`, `backrun` across `app/` returns only **a static `mev_exposure` LSTI component** at `app/collectors/lst_collector.py:46-95` and `app/index_definitions/lsti_v01.py:241` — this is a hand-coded per-LST integer (0-100 range), not ingested data.
- `app/data_layer/mempool_watcher.py` + `migrations/091_mempool_observations.sql` captures pending-tx observations for a watchlisted address set. With `input_data_truncated`, `function_selector`, `confirmation_latency_ms`, `from_address`, `to_address`, `seen_at_ms` — **this is the raw substrate for MEV inference** (sandwiches are detectable as ±-tx patterns around a victim tx). The collector is live (background loop in `app/worker.py:3310`). There is no *derived* layer that tags a sandwich / backrun / frontrun and joins it to asset.
- No EigenPhi / Flashbots-Data / libMEV ingestion. No cross-reference from `oracle_stress_events` or SII deviation events to MEV volume.

**This is a derivation-over-existing-state gap, not a new-collection gap.** The mempool substrate is being captured; the classifier isn't.

### Category H — Cross-chain state divergence for bridged assets

**Verdict: PARTIAL — registry merged, per-chain state partially preserved.**

**Evidence:**
- `app/indexer/config.py:135` maps `0xff970a61a04b1ca14834a43f5de4533ebddb5cc8` → `{"symbol":"USDC.e", ..., "stablecoin_id":"usdc"}`. The bridged variant is aliased to the canonical stablecoin entity at the indexer boundary, so `wallet_holdings` rolls up USDC.e into USDC.
- `wallet_chain_presence` (`migrations/096_wallet_chain_presence.sql`) records **per-wallet × per-chain** presence, not per-asset × per-chain supply.
- `app/data_layer/multichain_holder_collector.py` scans holders per chain but writes to the same `wallet_graph.wallets` table, not a per-chain supply time series for the asset itself.
- `app/collectors/defillama.py:131` stores `cross_chain_liquidity` as a scalar (number of chains) per asset — explicitly aggregated, not preserved as a per-chain breakdown.
- There is no "USDC.e on Avalanche supply at hour H" time-series table. CoinGecko `/coins/{id}/market_chart` (used via `app/data_layer/market_chart_backfill.py`) returns supply aggregated across chains.

**The rendering/collection boundary:** Per-chain supply for each bridged variant is fetch-able from CoinGecko's per-contract endpoint, Etherscan balanceOf on issuer contracts, or per-chain block explorer. The collection is simple; the decision that was made was to *alias*, and undoing that alias is both a schema change and an identity decision.

### Category I — Unstake queue depth and withdrawal latency

**Verdict: PARTIAL — thresholded static, observed latency not collected.**

**Evidence:**
- `app/index_definitions/lsti_v01.py:197-213` declares LSTI components `withdrawal_queue_impl` (source: `static`), `withdrawal_queue_length` (source: `empty`), `avg_withdrawal_time`, `withdrawal_success_rate`.
- `app/component_coverage.py:43-46` marks: `withdrawal_queue_impl=static`, `withdrawal_queue_length=empty`. The **rsETH audit** (`audits/internal/lsti_rseth_audit_2026-04-20.md`) confirms these components are declared-but-unwired; they are among the 8 null components causing the renormalization-defect blocker.
- `app/collectors/lst_collector.py:388-440::_automate_lst_withdrawal_queue` computes a `withdrawal_queue_impl` *score* from DeFiLlama protocol detail (whether the LST has an unstake mechanism implemented), but does NOT record queue depth or time-from-request-to-completion as a time series. It emits a scalar severity.
- No `lst_withdrawal_events` table. No `withdrawal_requested_at` / `withdrawal_completed_at` per request.

**The audit has already named this gap.** Four of the five "unwired" component names the LSTI rsETH audit flags are exactly Category I.

### Category J — Issuer disclosure publication latency

**Verdict: NOT COLLECTING.**

**Evidence:**
- `migrations/055_phase3_disclosure_tables.sql` creates `tti_disclosure_extractions` with columns `extracted_at`, `source_url`, `extraction_method`, `confidence`, `structured_data JSONB`. The *parsed disclosure* is captured; the publication date (the date the disclosure was *dated* by the issuer) is **inside `structured_data` but not a first-class column**.
- No column like `publication_date`, `disclosed_at`, `report_date`, `report_end_date`. Therefore no computable `publication_date - extracted_at` latency series.
- The TTI v0.1.0 index definition does not have an `issuer_disclosure_latency` component.
- `app/services/cda_collector.py` (which extracts reserve attestations for SII) writes `cda_vendor_extractions.extracted_at` but similarly does not canonicalise the issuer-stamped disclosure date.

**PW-14 on the tweet bank claims this as a signal.** It is currently observable only by manually parsing `structured_data` JSONB, not stored as a scored component or a plotted series.

### Category K — Protocol treasury composition trajectory

**Verdict: PARTIAL.**

**Evidence:**
- `migrations/026_protocol_treasury_holdings.sql` captures `protocol_treasury_holdings` with `protocol_slug, token_name, token_symbol, chain, usd_value, is_stablecoin, sii_score, snapshot_date DATE, created_at`. **Daily granularity, unique constraint on `(protocol_slug, token_symbol, chain, snapshot_date)`.** This IS a composition trajectory table.
- `migrations/041_treasury_registry.sql` adds `wallet_graph.treasury_registry` (labelled wallets) and `wallet_graph.treasury_events` (behavioural events — `twap_conversion`, `rebalance`, `concentration_drift`, `quality_shift`). Event-level, labelled.
- `app/collectors/treasury_flows.py::collect_treasury_events` is wired in `enrichment_worker.py` (`treasury_flows` task).

**So the trajectory data exists.** What is less clear (and I didn't fully verify) is whether the collection is daily-reliable across all 13 PSI protocols or whether it's sparse. The unique constraint on `snapshot_date` means at most one row per protocol-token-chain-day, so coverage is provable by row-count query. Provisionally PARTIAL pending a data-freshness check — if daily, this is COLLECTING; if sparse, it is PARTIAL.

### Category L — Oracle stress-event capture

**Verdict: COLLECTING.**

**Evidence:**
- `migrations/073_oracle_behavioral_record.sql` creates three tables: `oracle_price_readings` (per-reading price + deviation + latency + `is_stress_event` flag + `content_hash`/`attested_at`), `oracle_stress_events` (event-level with `max_deviation_pct`, `max_latency_seconds`, `concurrent_sii_score`, `concurrent_psi_scores`, `affected_protocols`), and `oracle_registry` (7 Chainlink + 1 Pyth seed feeds — ETH/USD, USDC/USD, USDT/USD, DAI/USD, BTC/USD, stETH/ETH, and Pyth USDC/USD on Base).
- `app/collectors/oracle_behavior.py` is wired in `app/worker.py:1576`. `app/data_layer/oracle_cadence_collector.py` + `migrations/093_oracle_update_cadence.sql` add round-update/gap tracking. `migrations/075_oracle_pre_stress_tagging.sql` adds pre-stress event correlation. `migrations/081_oracle_registry_feed_config.sql` manages feed config. `migrations/095_oracle_cadence_widen_columns.sql` widens those columns.
- `app/server.py:9586-9790` exposes `/oracle_readings_latest`, `/oracle_reading_history`, `/oracle_stress_events/list`, `/oracle_stress_events/active`, `/oracle_stress_events/{id}/triptych`, `/oracle_deviation_history`. The triptych endpoint surfaces "before / during / after" reading sets around a stress event.
- First commit of `oracle_behavior.py`: **2026-04-19** — so ~5 days of down-axis state as of this audit.

**The V9.5 one-pager claim "every oracle reading, every hour, across seven production feeds, with deviation and latency flagged at stress events" is SHIPPED.** Status: live, producing state, ~5 days into the historical record.

---

## Section 3 — Engineering Cost Estimates

Only categories verdicted **NOT COLLECTING** or **PARTIAL** are costed. Category L is out of scope.

| Cat | Data source | Collection pattern | Schema impact | Reference implementation | Cost tier |
|---|---|---|---|---|---|
| **A. Position state** | Aave v3 `UiPoolDataProviderV3`, Morpho Blue `MetaMorpho` vaults, Pendle `Market`/`YT`/`PT` subgraphs, Compound v3 Comet | Poll top N wallets × known markets; subgraph where possible, RPC `multicall` otherwise | **New entity class `position`.** New tables: `position_snapshots` (wallet, protocol, market, collateral_asset, debt_asset, collateral_amt, debt_amt, liq_threshold, health_factor, snapshot_at), `position_events` (open/modify/liquidate/close). Extends `protocol_pool_wallets` pattern. | `app/collectors/pool_wallet_collector.py` top-holder pattern; `app/collectors/morpho_blue.py` subgraph pattern | **HIGH** — new entity class, ≥ 10d for Aave+Morpho+Pendle, identity merging across them |
| **B. Liquidation cascade thresholds** | Existing `protocol_parameter_snapshots` × `protocol_pool_wallets` × live price series | Computed — periodic aggregation job, not a new collector | New table `liquidation_curves` (protocol, collateral_asset, snapshot_at, curve_points JSONB [{price_pct, liquidatable_notional_usd, affected_positions_count}]) | `app/data_layer/materialized_compositions.py` computed-aggregation pattern | **MEDIUM** — pure derived state, but depends on Category A to be meaningful; without A it can only express protocol-level curves against aggregate collateral, not positions |
| **C. Parameter-change downstream** | Already in DB: `protocol_parameter_changes.changed_at` × `entity_snapshots_hourly` × `liquidity_depth` × `mint_burn_events` | Computed — materialised view joining change timestamps to ±24/48/72h windows | New materialised view `parameter_change_impact_windows` or a `change_followup_stats JSONB` column on `protocol_parameter_changes`. No new collector. | `app/data_layer/materialized_compositions.py` | **LOW** — pure SQL + rendering |
| **D. Redemption friction** | Circle / Paxos public API for mint/redeem volume (where exposed), Etherscan tagged minter wallets for on-chain step | New collector polling issuer APIs + tagged-wallet event filter on `mint_burn_events` | New table `issuer_redemption_events` (issuer, direction, amount_usd, observed_on_chain_at, settled_off_chain_at, settlement_latency_s); add `issuer_tag` enum to `mint_burn_events` | Pattern: `app/services/cda_collector.py` adaptive waterfall | **MEDIUM** — API surface research required; some issuers don't expose this at all |
| **E. Delegate voting by proposal type** | Already in DB: `governance_proposals.votes JSONB`, `body`, `title` | Classifier + flattener. LLM-classify proposal bodies into {risk_parameter, treasury, integration, misc}; flatten JSONB `votes` into `delegate_votes` rows | New table `delegate_votes` (proposal_id, delegate_address, choice, vp, voted_at); add column `proposal_class` to `governance_proposals` (069 version). | `app/rpi/scorer.py` classification; `app/data_layer/wallet_behavior.py` flattener pattern | **MEDIUM** — classifier design + schema + backfill over already-captured proposals |
| **F. Insurance-fund depletion** | RPC `balanceOf` on: Aave Safety Module (stkAAVE), Morpho insurance, Compound COMP reserves, GMX insurance vault, SparkLend, Frax insurance | Polling collector, hourly | New table `insurance_fund_balances` (protocol, fund_address, asset, balance_wei, balance_usd, observed_at). Derived view `insurance_depletion_rate` joining with `rpi_components` revenue. | `app/collectors/treasury_flows.py` + `app/collectors/morpho_blue.py` RPC patterns | **LOW** — clean, well-bounded, ~10 known contracts |
| **G. MEV extraction** | `mempool_observations` (already live) + confirmed-tx classifier | Computed classifier over existing mempool + chain state. Optionally add Flashbots-Data / EigenPhi API as secondary source | New table `mev_events` (tx_hash, event_type [sandwich/backrun/frontrun/arb], extractor_address, victim_address, asset_involved, extracted_usd, detected_at); add `is_mev` flag to `mempool_observations` | `app/data_layer/wallet_behavior.py` classifier pattern on existing state | **MEDIUM** — classifier logic is non-trivial but substrate exists |
| **H. Cross-chain variants** | Etherscan `balanceOf` per bridged contract per chain, or CoinGecko per-contract market data | New polling collector at contract granularity; identity decision to un-alias | New entity rows in `stablecoins` for each bridged variant (or a child table `stablecoin_chain_variants`); new time series `per_chain_supply` | `app/collectors/etherscan.py` balance pattern | **MEDIUM → HIGH** — identity/aliasing decision ripples through `wallet_holdings`, `protocol_collateral_exposure`, SII scoring |
| **I. Unstake queue + withdrawal latency** | Beaconcha.in withdrawal queue API (ETH); Lido / Rocket Pool / Kelp / EtherFi protocol-specific contract events (e.g. `WithdrawRequested`, `WithdrawClaimed`) | Event-driven — RPC event subscribe on known withdrawal contracts | New table `lst_withdrawal_events` (lst_slug, request_tx, claim_tx, amount, requested_at, claimed_at, latency_s). Rewire four already-declared LSTI components. | `app/collectors/lst_collector.py:_automate_lst_withdrawal_queue` partial pattern | **MEDIUM** — per-LST adapter needed (each LST has different withdraw contract), but clearly scoped |
| **J. Disclosure publication latency** | Already ingested — publication date is in `tti_disclosure_extractions.structured_data` JSONB | Parser uplift: extract `publication_date` to first-class column at write time. Add CDA equivalent for stablecoin attestations. | Add column `publication_date DATE` to `tti_disclosure_extractions` and to `cda_vendor_extractions`. Backfill via JSONB extraction. | `app/services/tti_disclosure_collector.py::_store_extraction` | **LOW** — migration + 1 parser function |
| **K. Treasury trajectory** | Already being written to `protocol_treasury_holdings` daily | **Verify coverage breadth**. If 13 PSI protocols present daily, this is COLLECTING. If only a few present, extend to full PSI registry. | None if coverage is complete; otherwise extend collector loop over `psi_scores` registry. | `app/collectors/treasury_flows.py` | **LOW** — verification + coverage widening |

---

## Section 4 — Ranked Backlog

**Value-of-moat** is a 1-5 score answering: *how badly would a competitor starting in April 2028 want access to this 24-month historical record?*
**Cost** uses the tiers defined in Section 3.
**Ratio** = moat ÷ cost tier (3 for HIGH, 2 for MEDIUM, 1 for LOW).

| # | Collector | Current state | Moat (1-5) | Cost | Ratio | Recommendation |
|---|---|---|---|---|---|---|
| **1** | **F. Insurance-fund depletion time series** | NOT COLLECTING | 5 — "depletion curve of Aave Safety Module across 2026-2028" is not reconstructable from price data and not stored anywhere else | LOW | **5.0** | `START_THIS_WEEK` |
| **2** | **J. Disclosure publication latency as first-class column** | NOT COLLECTING | 4 — distinct from every other disclosure dataset because it measures *the issuer's own punctuality*. Uplift is tiny; state accrues forever. | LOW | **4.0** | `START_THIS_WEEK` |
| **3** | **C. Parameter-change downstream effects (SQL view)** | PARTIAL (rendering) | 4 — "what moved in the 72h after Aave raised GHO liquidation threshold" is a repeatedly-asked question. Computable from existing state. | LOW | **4.0** | `START_THIS_WEEK` |
| **4** | **K. Treasury trajectory coverage verification + extension** | PARTIAL | 3 — the table is right; coverage may be the gap. Low-cost either way. | LOW | **3.0** | `START_THIS_WEEK` if extension needed; `ALREADY_COVERED_NO_ACTION` if verify passes |
| **5** | **I. Unstake queue + withdrawal latency** | PARTIAL — declared but 4/5 LSTI components null | 5 — unblocks LSTI publication (V9.4 gate). Observed latency has no substitute data source. | MEDIUM | **2.5** | `START_NEXT_SPRINT` |
| **6** | **E. Delegate voting by proposal type** | PARTIAL (JSONB captured, not classified) | 5 — Mantle-Aave makes this acutely relevant. Competitors in 2028 cannot reconstruct who voted on risk parameters over 24 months. | MEDIUM | **2.5** | `START_NEXT_SPRINT` |
| **7** | **G. MEV during stress** | NOT COLLECTING (classifier) — substrate live | 4 — MEV-during-depeg is a distinctive measurement; mempool substrate already accruing. Pure derivation. | MEDIUM | **2.0** | `START_NEXT_SPRINT` |
| **8** | **D. Issuer-direct redemption friction** | NOT COLLECTING | 5 — tells you whether 1:1 promise holds under stress. No one else is sampling this. | MEDIUM | **2.5** | `SCHEMA_WORK_FIRST` — issuer API inventory required |
| **9** | **B. Liquidation cascade curves** | NOT COLLECTING | 5 (if done after A) — the single most-asked question about tail risk | MEDIUM | **2.5** | `SCHEMA_WORK_FIRST` — depends on A for position-level precision |
| **10** | **A. Position-entity state** | NOT COLLECTING | 5 — the most valuable dataset on this list over 24 months, because it is the only one that would require reconstructing *continuous leverage configurations* that don't exist in any other form | HIGH | **1.7** | `SCHEMA_WORK_FIRST` — new entity class + identity + merging is a multi-week architectural change |
| **11** | **H. Cross-chain variant series** | PARTIAL (aliased) | 4 — bridge-embedded risk is real, but identity decision is politically loaded (SII scoring already assumes canonical entity) | MEDIUM → HIGH | **1.3–2.0** | `SCHEMA_WORK_FIRST` — aliasing decision must be made before any collector work |

The three `SCHEMA_WORK_FIRST` items are high-value; they are not deferred, they are blocked on a schema decision that needs a human.

---

## Section 5 — Summary and Schema Questions

### Top 3 `START_THIS_WEEK`

1. **Insurance-fund depletion** (F) — New table + ~10 known RPC `balanceOf` calls on an hourly loop. Pattern from `treasury_flows`. Highest ratio on the board.
2. **Disclosure publication latency first-class column** (J) — A migration adding `publication_date DATE` to `tti_disclosure_extractions` and `cda_vendor_extractions`, plus one parser extraction step. Backfillable.
3. **Parameter-change downstream SQL view** (C) — A materialised view joining existing `protocol_parameter_changes.changed_at` to ±24/48/72h windows across `entity_snapshots_hourly`, `liquidity_depth`, `mint_burn_events`. No new collector.

### Top 3 `START_NEXT_SPRINT`

1. **Unstake queue + withdrawal latency** (I) — Wires up four LSTI components already declared null in the rsETH audit. Unblocks V9.4 LSTI publication gate.
2. **Delegate voting by proposal type** (E) — Classifier over existing `governance_proposals.votes` JSONB + flatten into `delegate_votes`. Moat is acute because of the Mantle-Aave delegation situation.
3. **MEV during stress** (G) — Classifier over `mempool_observations` + chain state. Substrate is already accruing; this is pure derivation.

### `SCHEMA_WORK_FIRST` items and the questions that must be answered before collectors start

**A. Position-entity state** — questions requiring a human decision:

1. Is `position` a first-class entity with its own ID, or a JSON sub-record of a wallet?
2. How do we merge "same user, same protocol, different market" into a position cluster? (Aave wallets have one position per reserve; Morpho has one per market; Pendle has one per PT expiry.)
3. When a PT expires, does the position row persist with `status=expired`, or does it reset?
4. Is `health_factor` stored as a snapshot at every poll, or only at change events?

**B. Liquidation cascade curves** — blocks on A, plus one local decision:

1. Are curves stored as JSONB (list of price-point → notional tuples) per protocol-asset per snapshot, or as a sparse two-dimensional table?

**D. Issuer-direct redemption friction** — blocks on external research:

1. Which issuers publish mint/redeem via API (Circle? Paxos? First Digital?), which only via blog post, which not at all?
2. Can on-chain minter-wallet tagging substitute where API isn't available?

**H. Cross-chain variant series** — blocks on an identity decision, not on engineering:

1. Do we treat USDC.e as a child entity of USDC (preserves SII simplicity, loses bridge-risk dimension) or as a peer entity (requires SII methodology amendment)?
2. If child, do we add a `chain_variant_supply` table keyed on `(parent_stablecoin_id, chain, contract_address)` that preserves per-chain state without changing the scoring entity?
3. How does `wallet_holdings` behave — currently it rolls up, and un-rolling has performance cost.

Until these questions are answered, collectors in categories A, B, D, H should not be started — the schema decision would trap the down-axis state in a shape that's expensive to migrate later.

---

## Section 6 — Additional Categories from the Step-5 Honesty Check

The 12 prompted categories share a framing ("position state, cascade state, flow state"). Pausing to ask what's missing surfaced five additional candidates. Each is analysed with the same method. Two are upgraded to ranked entries; three are flagged and deferred for the reasons given.

### Category M — Validator slashing event series

**Verdict: NOT COLLECTING.**

**Evidence:** Grep for `slashing_event`, `slashing_record` returns no collector. `app/collectors/lst_collector.py:12` notes "beaconcha.in: validator counts, slashing events (free tier)" — named as a future source. The LSTI rsETH audit lists `slashing_history` as one of five "unwired collector code" components. `rated_validators.py` ingests Rated Network but that has a known 6-of-10 LST coverage gap.

**Moat:** 4 — slashing is the precursor event for LST peg breaks. Missing it for 24 months = missing the defining LST-risk dataset.
**Cost:** LOW — beaconcha.in public API, ~1 day.
**Ratio: 4.0. Recommendation: `START_THIS_WEEK`.**

This is arguably the single clearest omission — it was *named* in the LSTI audit as a gap and is untracked.

### Category N — Gas-price spike correlation per asset

**Verdict: NOT COLLECTING (time series), STATIC (scoring input).**

**Evidence:** Grep for `gas_price_event`, `gas_spike_*` returns no table. `app/data_layer/correlation_engine.py:7` mentions gas spikes but does not collect gas-fee time series. `app/collectors/derived.py:20` uses gas-spike susceptibility as a *static* per-chain score component.

**Moat:** 3 — gas-spike history correlated with redemption / liquidation events is useful for stress analysis, but Etherscan / Alchemy preserve the raw base-fee history anyway. Reconstruction is possible.
**Cost:** LOW — one RPC collector polling base fee + priority fee hourly; ~1 day.
**Ratio: 3.0. Recommendation: `START_NEXT_SPRINT` — moderate value, not a unique-to-Basis record.**

### Category O — Forum-sentiment change before proposals

**Verdict: NOT COLLECTING (sentiment signal); ingesting raw posts.**

**Evidence:** `app/rpi/forum_scraper.py` ingests governance forum posts to `governance_forum_posts`. Grep for `sentiment`, `forum_sentiment`, `polarity` returns no sentiment-scored series. Raw text is captured; scored delta over time is not.

**Moat:** 2 — sentiment analysis is noisy, and dozens of off-the-shelf competitors already produce this. Not unique-to-Basis. Our value would be the *correlation* to subsequent score changes, not the sentiment itself.
**Cost:** MEDIUM — requires an LLM or sentiment classifier + backfill + daily polling.
**Ratio: 1.0. Recommendation: `DEFER_WITH_DOCUMENTATION`.**

### Category P — Liquidity migration events (pool moves > threshold)

**Verdict: PARTIAL — raw pool data collected, migration events not derived.**

**Evidence:** `app/data_layer/liquidity_collector.py` writes `liquidity_depth` continuously. `app/collectors/dex_pools.py` writes `dex_pool_data` via `generic_index_scores` 3h-gated. Grep for `liquidity_migration`, `pool_migration`, `tvl_migration` returns no table. Large pool movements are *visible* in the data but not *flagged* as events.

**Moat:** 3 — "when did X tokens migrate from Curve 3pool to Uniswap stableswap" is a concrete question. Recoverable from stored state, so the derived-events table is a rendering/aggregation task.
**Cost:** LOW — SQL over existing `liquidity_depth`.
**Ratio: 3.0. Recommendation: `START_NEXT_SPRINT`.**

### Category Q — Cross-protocol wallet behaviour patterns

**Verdict: PARTIAL.**

**Evidence:** `app/data_layer/wallet_behavior.py` + `wallet_behavior_tags` exist and run daily. This already captures *per-wallet* behaviour signatures. What's less clear is whether cross-protocol *patterns* (looping between Pendle and Aave; Curve LP + Convex stake; etc.) are tagged — the `wallet_profile_v1` spec at `app/specs/wallet_profile_v1.py` hints at this. Without reading every behavioural tag definition I can't rule this in or out.

**Moat:** 3 — overlaps with Category A's position-entity work.
**Cost:** Depends on what `wallet_behavior_tags` already does. Unknown — **PARTIAL PENDING VERIFICATION**.
**Recommendation:** `DEFER_WITH_DOCUMENTATION` until the `wallet_behavior` tag registry is separately audited.

### Updated ranked position for new entries

Only two of the five new entries clear the `DEFER_WITH_DOCUMENTATION` bar. Inserted into the Section 4 ranking:

- **Category M — Validator slashing history.** Tier: LOW cost, moat 4, ratio 4.0 → `START_THIS_WEEK`. Places **between #2 and #3** on the overall ranked list.
- **Category P — Liquidity migration events (derived).** Tier: LOW, moat 3, ratio 3.0 → `START_NEXT_SPRINT`. Places **around #6** on the overall ranked list.
- **Category N — Gas-price time series.** Tier: LOW, moat 3, ratio 3.0 → `START_NEXT_SPRINT`. Moderate value.

So the effective `START_THIS_WEEK` set is:

1. **F** — Insurance-fund depletion
2. **J** — Disclosure publication latency
3. **M** — Validator slashing history
4. **C** — Parameter-change downstream SQL view
5. **K** — Treasury trajectory coverage verification/extension

### Final honesty notes (Step 5 checklist)

1. **"Collecting" vs "produced some rows"** — most of the `COLLECTING` verdicts in Section 2 refer to live wiring in `enrichment_worker.py`, not row-count audits. The earliest collector commit is **2026-04-13**, so *every* down-axis series in this system is at most 11 days long as of audit date. A separate row-count-and-freshness audit should run once the easy `START_THIS_WEEK` items land, to confirm no silent failures.
2. **Docs vs schema** — I weighted the code/schema higher than the canonical docs whenever they disagreed. Example: v9.3 says bridge flows are deferred; `main.py` still has a wiring block; I treated the `enrichment_worker.py` comment ("Tier 4 — DEFERRED") as authoritative and flagged the `main.py` path as stale rather than the deferral doc as wrong.
3. **Framing inheritance** — the robtg4 "PTs as looper infrastructure" framing was visible in Category A. The Step-5 pass deliberately surfaced Categories M / N / O / P / Q which come from different framings (validator risk, gas surface, sentiment, liquidity topology, wallet behaviour composition) to hedge against that.
4. **Rendering vs collection** — flagged explicitly for **C** (derived view), **E** (classifier), **G** (classifier), **K** (may be coverage only), **P** (derived events). These are cheaper than new collectors and should land first if the decision-maker values shipping over comprehensiveness.
5. **Unverified claims that should be re-audited** — (a) Category K daily coverage breadth; (b) Category Q wallet-behaviour-tag registry content; (c) ~~whether the 14 orphaned attestation domains are genuine gaps or merely renamed-and-forgotten domains from earlier architecture~~ — **resolved 2026-04-24: all 14 domains are wired; the actual gap is payload-vs-domain-name mismatch in `psi_components`/`rpi_components`, plus a missing entry for `rpi_components` in the state-root composition list (see corrected Section 1.4).**

---

*End of audit. Section 1.4 corrected 2026-04-24 following ENG-TICKET re-investigation.*







