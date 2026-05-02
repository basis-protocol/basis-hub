# Phase 2 Sync-In-Async Campaign — Closure Report

**Date:** 2026-05-01 → 2026-05-02
**Outcome:** mint_burn_events unblocked after 222h staleness. Worker hot path clean.

## What shipped

12 commits across the day on `main`:
- fe995a8 — phase 1 instrumentation
- 4ef2cca — PR 1: edge builder hot path
- 2f49f7d — PR 2: data_layer background loops
- 077f3dd — PR 3: collectors hot path
- 7fa8601, eb492f8 — schema fixes (catalog created_at, regulatory_registry_checks)
- 771560e — PR 4: worker.py main + helpers + db_schema_validator
- bd79153 — PR 5: remaining batch (~100 sites, 25 files)
- 1b43bfa — PR 5 fix: 24 unawaited callers caught pre-merge
- fcef14e — hotfix: integrity.py dispatch loop + morpho_blue.py asyncio.run
- 58791eb — hotfix #2 part 2: worker.py wait_for(await ...) + aliased imports
- a8040d6 — hotfix #3: sync collectors needed asyncio.to_thread

Two manual migrations against Neon:
- 059_provenance_columns.sql — added provenance_proof_id to 12 tables
- 103_regulatory_registry_checks.sql — created missing table

## Phase 3 deferred

`_warn_if_async_context` still emits `logger.error` rather than `RuntimeError`. Promotion to RuntimeError would crash production because ~100+ sync-in-async sites remain across:

- `app/server.py` — FastAPI startup and seeding (~7 sites)
- `app/ops/routes.py` — HTTP route handlers (~137 sites, only fire on traffic)
- `app/indexer/api.py` — indexer HTTP handlers (~40 sites, same)
- `app/publisher/*` — daily pulse rendering
- `app/scripts/backfill/*` — CLI scripts run separately (out-of-process)
- `app/rpi/*` — RPI scoring stack (sync, called from async wrappers without to_thread)
- `app/services/cda_collector.py`, `app/services/contagion_archive.py` (some sites)
- `app/data_layer/{entity_snapshots, contract_surveillance, holder_discovery, correlation_engine, wallet_behavior, ohlcv_collector, incident_detector}.py` — sync collectors
- `app/collectors/{dex_pools, governance_events, web_research, dao_collector}.py` — sync
- `app/state_attestation.py:51, 85` — deliberately reverted to sync (best-effort)
- `app/utils/rpc_provider.py:219 (_track)` — deliberately reverted to sync (best-effort)
- `app/data_layer/state_growth.py:187 (snapshot_row_counts)` — out-of-PR-5-scope

Phase 3 sequence: convert these in dedicated PRs, then promote the warning to RuntimeError. No urgency — system is stable as-is and the audit trail is preserved via logger.error.

## Lessons

- Mass automated conversion (PR 5) needed pre-merge static audit AND post-deploy runtime validation. Static AST audit caught 24 unawaited callers. Runtime surfaced 6 more (dispatch tables, asyncio.run inside event loop, aliased imports).
- Dispatch table pattern (`for fn in fns: result = fn()`) defeats grep-based audits. Mark these as known patterns to look for.
- `asyncio.run()` inside sync function called from async context (without to_thread wrapping) is a footgun. Multiple instances surfaced.
- `await asyncio.wait_for(await fn(), ...)` is a common conversion mistake — drops timeout protection AND throws TypeError.
- Aliased imports (`from app.database import fetch_one as _fo`) bypassed regex converters. Worth a separate pass to normalize.

## Operational TODOs filed

See git log for individual cleanup commits.
