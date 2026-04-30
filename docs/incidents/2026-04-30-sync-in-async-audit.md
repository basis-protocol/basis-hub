# Sync-in-Async Anti-Pattern Audit

**Date:** 2026-04-30
**Scope:** All files under `app/` with `async def` functions containing naked sync DB calls (`fetch_one`, `fetch_all`, `execute`, `get_cursor`)
**Excluded:** `app/api_usage_tracker.py` (fixed f49c5b9), `app/data_layer/mint_burn_collector.py` (pending fix), `app/database.py` (defines the functions)

## Inventory

| File | Line | Function context | Sync call | Severity | Notes |
|------|------|-----------------|-----------|----------|-------|
| app/server.py | ~380-2500 | 118 async request handlers | fetch_one ×69, fetch_all ×125, execute ×13 | HIGH | Every public API handler. Zero wrapping. 207 naked calls total |
| app/ops/routes.py | ~97-1225 | 54 async request handlers | fetch_one ×54, fetch_all ×53, execute ×41 | HIGH | Every ops route handler. Zero wrapping. 148 naked calls total |
| app/indexer/api.py | 35-983 | 23 async request handlers | fetch_one ×24, fetch_all ×14, execute ×2 | HIGH | All wallet API handlers. Zero wrapping. 40 naked calls |
| app/worker.py | 703-919 | run_fast_cycle (async) | fetch_all ×7, fetch_one ×5 | HIGH | Primary scoring loop, naked calls for diagnostics/provenance |
| app/worker.py | 1108-1509 | run_fast_cycle data layer section | get_cursor ×8 | HIGH | Per-entity inner loop, cursor.execute directly in async |
| app/worker.py | 1757-2503 | run_slow_cycle (async) | fetch_one ×11, fetch_all ×2 | MEDIUM | Gate queries, once per slow cycle |
| app/worker.py | 3021-3438 | main (async) startup DDL | execute ×20+, fetch_one ×4 | LOW | Startup only, runs once |
| app/data_layer/wallet_expansion.py | 48-94 | run_wallet_graph_expansion (async) | fetch_all ×3, fetch_one ×3 | HIGH | Multiple sync reads before per-address hot loop |
| app/data_layer/wallet_expansion.py | 220 | run_wallet_graph_expansion (async) | get_cursor | HIGH | Inside per-address loop (up to 10K addresses) |
| app/data_layer/wallet_expansion.py | 282-408 | run_multi_source_seeding (async) | fetch_one ×6, get_cursor ×3, fetch_all ×1 | HIGH | Per-holder inner loop |
| app/data_layer/peg_monitor.py | 235 | run_peg_monitoring (async) | fetch_all | MEDIUM | Single read before per-coin loop |
| app/data_layer/peg_monitor.py | 113-221 | _store_peg_snapshots/_store_volatility_surface (sync helpers from async) | get_cursor ×3 | HIGH | Per-coin inside loop |
| app/data_layer/peg_monitor.py | 303-344 | run_peg_monitoring (async) | get_cursor, execute | HIGH | Per-coin and per-depeg loops |
| app/data_layer/trace_collector.py | 77-89 | run_trace_collection (async) | fetch_all ×2 | HIGH | Entry point before per-protocol loop |
| app/data_layer/trace_collector.py | 209 | run_trace_collection (async) | get_cursor | HIGH | Inside per-tx hot loop |
| app/data_layer/trace_collector.py | 285 | trace_collector_background_loop (async) | fetch_one | MEDIUM | Gate check once per tick |
| app/data_layer/multichain_holder_collector.py | 44 | _get_blockscout_24h_usage (sync from async) | fetch_one | MEDIUM | Gate check once per scan |
| app/data_layer/multichain_holder_collector.py | 156-193 | run_multichain_holder_scan (async) | get_cursor ×3 | HIGH | Inside nested per-holder loop |
| app/data_layer/multichain_holder_collector.py | 248 | multichain_holder_background_loop (async) | fetch_one | MEDIUM | Gate check per tick |
| app/data_layer/market_chart_backfill.py | 256 | run_market_chart_backfill (async) | fetch_all | HIGH | Entry point load |
| app/data_layer/market_chart_backfill.py | 278 | run_market_chart_backfill (async) | fetch_one | HIGH | Inside per-coin loop |
| app/data_layer/market_chart_backfill.py | 117-221 | _store_market_chart_records/_store_volatility_surface (sync from async) | get_cursor ×3 | HIGH | Per-coin inside loop |
| app/data_layer/markets_collector.py | 193 | run_bulk_markets (async) | fetch_all | MEDIUM | Called once per cycle |
| app/data_layer/markets_collector.py | 144 | _store_markets_data (sync from async) | get_cursor | HIGH | Per-entity inside loop |
| app/data_layer/oracle_cadence_collector.py | 137 | _sample_oracles (async) | get_cursor | HIGH | Inside per-oracle hot loop |
| app/data_layer/ohlcv_collector.py | 161 | _get_tracked_pools_tiered (sync from async) | fetch_all | MEDIUM | Called once at start |
| app/data_layer/ohlcv_collector.py | 124 | _store_ohlcv_records (sync from async) | get_cursor | HIGH | Per-pool inside nested loop |
| app/data_layer/yield_collector.py | 150 | _store_yield_snapshots (sync from async) | get_cursor | HIGH | Per-snapshot inner loop |
| app/data_layer/yield_collector.py | 236 | run_yield_collection (async) | fetch_one | HIGH | Inside per-pool loop |
| app/data_layer/wallet_presence_scanner.py | 39 | _get_blockscout_24h_usage (sync from async) | fetch_one | MEDIUM | Gate check |
| app/data_layer/wallet_presence_scanner.py | 60-81 | run_wallet_presence_scan (async) | fetch_all ×2 | HIGH | Before per-wallet loop |
| app/data_layer/wallet_presence_scanner.py | 131 | run_wallet_presence_scan (async) | get_cursor | HIGH | Inside per-wallet × per-chain loop |
| app/data_layer/wallet_presence_scanner.py | 189-195 | wallet_presence_background_loop (async) | fetch_one ×2 | MEDIUM | Gate checks per tick |
| app/data_layer/transfer_edge_builder.py | 37 | _get_etherscan_24h_usage (sync from async) | fetch_one | MEDIUM | Budget gate per batch |
| app/data_layer/transfer_edge_builder.py | 47 | _get_wallets_for_scan (sync from async) | fetch_all | MEDIUM | Called once per batch |
| app/data_layer/transfer_edge_builder.py | 150-174 | _process_wallet (async) | execute ×2 | HIGH | Per-edge inside per-wallet loop |
| app/data_layer/approval_collector.py | 47-69 | run_approval_collection (async) | fetch_all, fetch_one | HIGH | Entry point wallet load |
| app/data_layer/approval_collector.py | 168 | run_approval_collection (async) | fetch_one | HIGH | Per-wallet per-approval inner loop |
| app/data_layer/approval_collector.py | 260-267 | approval_collector_background_loop (async) | fetch_one ×2 | MEDIUM | Gate checks per tick |
| app/data_layer/contract_surveillance.py | 205 | _detect_changes (sync from async) | fetch_one | HIGH | Per-contract inside loop |
| app/data_layer/contract_surveillance.py | 233 | run_contract_surveillance (async) | fetch_all | MEDIUM | Entry point load |
| app/data_layer/contract_surveillance.py | 358 | run_contract_surveillance (async) | execute | MEDIUM | Signal emit |
| app/data_layer/entity_discovery.py | 75-86 | _get_existing_entities (sync from async) | fetch_all ×2 | MEDIUM | Called once per cycle |
| app/data_layer/entity_snapshots.py | 160-187 | run_entity_snapshots (async) | fetch_all ×2 | HIGH | Before per-entity loop |
| app/data_layer/holder_discovery.py | 141 | run_holder_discovery (async) | fetch_all | HIGH | Loads all wallets at start |
| app/data_layer/holder_ingestion_collector.py | 70 | _build_entity_specs (sync from async) | fetch_all | HIGH | Stablecoin spec load |
| app/data_layer/holder_ingestion_collector.py | 418-424 | holder_ingestion_background_loop (async) | fetch_one ×2 | MEDIUM | Gate checks per tick |
| app/data_layer/liquidity_collector.py | 320 | run_liquidity_collection (async) | fetch_all | HIGH | Before per-stablecoin loop |
| app/data_layer/bridge_flow_collector.py | 112 | _store_bridge_flows (sync from async) | get_cursor | HIGH | Per-bridge inside loop |
| app/data_layer/exchange_collector.py | 150 | _store_exchange_data (sync from async) | get_cursor | HIGH | Per-exchange inside loop |
| app/data_layer/governance_collector.py | 235-294 | _store_proposals/_store_voters (sync from async) | get_cursor ×2 | HIGH | Per-proposal/per-voter loops |
| app/data_layer/mempool_watcher.py | 106-117 | build_watchlist (sync from async) | fetch_all ×2 | MEDIUM | Per reconnect cycle |
| app/data_layer/mempool_watcher.py | 167-182 | _current_hour_cu/_rolling_24h_cu (sync from async) | fetch_one ×2 | MEDIUM | Per reconnect |
| app/data_layer/mempool_watcher.py | 503 | reconcile_once (async) | fetch_all | HIGH | Per-tick reconciliation |
| app/data_layer/mempool_watcher.py | 549-567 | reconcile_once (async) | execute ×2 | HIGH | Inside per-tx loop (up to 500) |
| app/data_layer/prover_source_registry.py | 311 | run_provenance_health_recheck (async) calls sync helpers | fetch_all, execute, fetch_one | MEDIUM | Daily recheck, slow path |
| app/indexer/edges.py | 186-207 | build_edges_for_wallet (async) | execute ×2 | HIGH | Per-wallet in hot loop |
| app/indexer/edges.py | 252-273 | run_edge_builder (async) | fetch_all, fetch_one ×2 | HIGH | Batch load + diagnostics |
| app/indexer/edges.py | 317 | run_edge_builder error path (async) | execute | HIGH | Per-wallet error recovery |
| app/indexer/edges.py | 362-438 | decay_edges/prune_stale_edges (sync from async) | execute ×3, fetch_one ×3 | HIGH | Called directly without await from async |
| app/indexer/edges.py | 452-478 | edge_builder_background_loop (async) | fetch_one ×2 | MEDIUM | Gate checks per tick |
| app/indexer/expander.py | 79-150 | run_wallet_expansion (async) | fetch_all, execute ×3 | HIGH | Per-coin/per-holder hot loop |
| app/indexer/pipeline.py | 380-388 | discover_new_tokens (async) | fetch_all | HIGH | Per-wallet discovery |
| app/indexer/pipeline.py | 660-688 | run_pipeline_batch (async) | fetch_all, fetch_one ×2 | HIGH | Pipeline entry |
| app/indexer/pipeline.py | 838-889 | run_pipeline (async) | fetch_one, fetch_all | HIGH | Startup ping + filter |
| app/indexer/solana_edges.py | 171-192 | build_solana_edges_for_wallet (async) | execute ×2 | HIGH | Per-edge upsert loop |
| app/indexer/solana_edges.py | 228 | run_solana_edge_builder (async) | fetch_all | HIGH | Wallet query before loop |
| app/publisher/page_renderer.py | 97-169 | wallet_page (async) | fetch_one ×2, fetch_all ×3 | HIGH | Request handler, 5 calls |
| app/publisher/page_renderer.py | 204-228 | asset_page (async) | fetch_one, fetch_all | HIGH | Request handler |
| app/publisher/page_renderer.py | 236 | assessment_page (async) | fetch_one | HIGH | Request handler |
| app/publisher/page_renderer.py | 270 | pulse_page (async) | fetch_one | HIGH | Request handler |
| app/publisher/page_renderer.py | 316-324 | sitemap_xml (async) | fetch_all ×4 | HIGH | Request handler |
| app/payments.py | 247-567 | 9 paid_* handlers (async) | fetch_one/fetch_all per handler | HIGH | Every paid request handler |
| app/payments.py | 202 | _log_payment (sync from async handlers) | execute | MEDIUM | Called from all paid handlers |
| app/agent/api.py | 45-130 | 6 async request handlers | fetch_all ×2, fetch_one ×4 | HIGH | Assessment API handlers |
| app/collectors/oracle_behavior.py | 364-547 | tag_pre_stress/handle_stress/close_stress (sync from async) | get_cursor, fetch_one ×5, execute ×2, fetch_all | HIGH | Per-oracle async tasks |
| app/collectors/treasury_flows.py | 65-431 | 5 sync helpers from async loop | fetch_all ×5, fetch_one ×2 | HIGH | Per-wallet/per-transfer hot loop |
| app/collectors/parameter_history.py | 243-523 | 4 sync helpers from async | fetch_one ×5, fetch_all ×2, execute ×3 | HIGH | Per-change/per-protocol loops |
| app/collectors/governance_proposals.py | 146-431 | sync helpers from async loop | fetch_one ×2, execute ×3 | HIGH | Per-protocol/per-proposal loops |
| app/collectors/contract_dependencies.py | 161-405 | sync helpers from async loop | fetch_all ×2, fetch_one ×2, execute ×3 | HIGH | Per-entity hot loop |
| app/collectors/clustered_concentration.py | 118-144 | _compute_clusters (sync from async) | fetch_all ×2 | HIGH | Per-coin inside loop |
| app/collectors/on_chain_cda.py | 141 | _store_on_chain_reading (sync from async) | get_cursor | HIGH | Per-asset loop |
| app/collectors/solana_program_monitor.py | 165-215 | sync helpers from async | get_cursor, fetch_one, execute | HIGH | Per-program loop |
| app/collectors/web_research.py | 400 | _store_research_component (sync from async) | execute | HIGH | Per-entity/component loop |
| app/collectors/etherscan.py | 390 | _estimate_total_supply (sync from async) | fetch_one | HIGH | Per-coin enrichment |
| app/collectors/regulatory_scraper.py | 382 | check_exchange_regulatory (sync from async) | execute | MEDIUM | Once per exchange per cycle |
| app/collectors/dao_collector.py | 271-848 | 3 sync helpers from async chain | fetch_one ×2, execute | MEDIUM | Once per DAO per cycle |
| app/ops/tools/governance_monitor.py | 57-373 | scan_snapshot/scan_tally/helpers (async) | fetch_one ×6, execute ×5 | HIGH | Per-target/per-proposal loops |
| app/ops/tools/investor_monitor.py | 60-308 | 4 async functions | fetch_one ×5, fetch_all, execute ×5 | HIGH | Per-investor/per-item loops |
| app/ops/tools/twitter_monitor.py | 26-123 | scan/scan_handle (async) | fetch_all ×2, fetch_one, execute | HIGH | Per-target/per-tweet loops |
| app/ops/tools/news_monitor.py | 105-122 | scan_news (async) | fetch_one, execute | HIGH | Per-news-item loop |
| app/ops/tools/oracle_monitor.py | 140-273 | _poll_chain/_poll_contract (async) | fetch_one ×2, execute | HIGH | Per-log/per-tx loops |
| app/ops/tools/drafter.py | 59-84 | sync helpers from async | fetch_one, fetch_all ×4 | HIGH | Called from draft_dm/draft_forum_post |
| app/ops/tools/alerter.py | 78-214 | send_alert/check_* (async) | fetch_one ×2, fetch_all, execute ×2 | MEDIUM | Per-alert path |
| app/ops/tools/analyzer.py | 68-131 | analyze_content (async) | fetch_one, execute | MEDIUM | Once per content item |
| app/ops/tools/scraper.py | 19-57 | scrape_target (async) | fetch_one ×2, execute | MEDIUM | Once per scrape |
| app/services/cda_collector.py | 393-1364 | 7 async functions | fetch_one ×4, fetch_all ×2, execute ×3 | MEDIUM | Per-issuer waterfall steps |
| app/services/historical_backfill.py | 267-271 | backfill_coin/backfill_all (async) | calls sync versions directly | MEDIUM | Async wrappers call sync with DB inline |
| app/enrichment_worker.py | 71-208 | _execute_task gate_check (async) | fetch_one via make_db_gate | MEDIUM | ~15 gate checks per cycle, sync closure from async |
| app/governance.py | 751-784 | 4 async route handlers | call sync helpers with get_conn | HIGH | get_stats/get_hot_debates use raw get_conn |
| app/mcp_server.py | 34-57 | _log_mcp_tool_call → _flush_mcp_log (sync from async) | get_conn + cursor.execute | MEDIUM | Inline flush at buffer=20, same pattern as tracker |
| app/utils/rpc_provider.py | 218-460 | probe_rpc_capabilities (async) | execute ×2 | MEDIUM | Called during probe, not hot path |
| app/utils/data_source_comparator.py | 49-375 | compare_* (async) | fetch_one ×3, fetch_all ×2, execute | MEDIUM | Per-comparison calls |

### Correctly Wrapped (for reference)

| File | Pattern | Notes |
|------|---------|-------|
| app/collectors/flows.py | run_in_executor for 6 sync helpers | Correct |
| app/collectors/registry.py | run_in_executor for sync collectors | Correct |
| app/data_layer/mempool_watcher.py | run_in_executor for _insert/_attest | Correct |
| app/engine/analysis_persistence.py | asyncio.to_thread for all DB | Correct |
| app/engine/approval.py | asyncio.to_thread | Correct |
| app/engine/artifact_persistence.py | asyncio.to_thread for all DB | Correct |
| app/engine/event_pipeline.py | asyncio.to_thread | Correct |
| app/engine/event_sources/*.py | asyncio.to_thread | Correct |
| app/engine/events_router.py | asyncio.to_thread for all DB | Correct |
| app/engine/watchlist.py | asyncio.to_thread for all DB | Correct |
| app/worker.py score_stablecoin | run_in_executor for store_* calls | Correct |
| app/worker.py health/coherence | asyncio.to_thread | Correct |
| app/data_layer/oracle_cadence_collector.py:92 | fetch_all_async | Correct |

## Summary

**Total naked sync-DB-in-async call sites:** ~530+
**By severity:**
- HIGH: ~420 (request handlers, hot loops, per-entity/per-wallet paths)
- MEDIUM: ~90 (once-per-cycle gates, admin endpoints, slow paths)
- LOW: ~20 (startup, error recovery)

## Top 3 Highest-Priority Files to Fix

1. **app/server.py** — 207 naked calls across 118 async request handlers. Every production API request blocks the event loop. Highest user-facing impact. Fix: wrap all DB calls in `asyncio.to_thread` or convert to `fetch_one_async`/`fetch_all_async`.

2. **app/indexer/api.py** — 40 naked calls across 23 wallet API handlers. Every wallet lookup, profile view, and graph query blocks the loop. Second-highest user-facing impact after server.py.

3. **app/data_layer/wallet_expansion.py** — 16 naked calls including `get_cursor` inside a per-address loop processing up to 10K addresses. Causes the 1077s enrichment runtime. Directly explains the wallet_behavior stall pattern observed in production.

**Runner-up:** app/ops/routes.py (148 calls, 54 handlers) — lower priority only because ops traffic is admin-only.
