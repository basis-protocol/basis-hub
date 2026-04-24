**TITLE:** Basis Analytic Engine — Step 0 Artifacts

**CONTEXT:** Read `docs/analytic_engine_step_0_v0.2.md` (or whichever v0.x is latest) before starting. It is the contract for the engine. These artifacts must match it exactly.

**SCOPE:** Four deliverables, one commit. Do NOT create `app/engine/` beyond what's specified. Do NOT implement any handlers. This is preparation only.

**COMMIT MESSAGE:** `engine: step 0 artifacts — fixtures + schema additions + sql patch`

---

**DELIVERABLE 1: Schema file with two new fields**

Create `app/engine/schemas.py` containing the complete Pydantic schema from §1 of the Step 0 document, with two additions to `EntityCoverage` positioned between `unique_days` and `data_source`:

- `days_since_last_record: Optional[int] = None` — integer days between reference date and `latest_record`. 0 = today, 2 = 2 days stale.
- `coverage_window_days: Optional[int] = None` — integer days between `earliest_record` and `latest_record`. Null if fewer than 2 records.

Also update the markdown document's §1 schema block to match the Python file exactly. Bump document version to v0.3. Add changelog entry: "v0.3 — added days_since_last_record and coverage_window_days to EntityCoverage; generated canonical fixtures."

---

**DELIVERABLE 2: Canonical coverage fixtures**

Create `tests/fixtures/canonical_coverage.py`.

**Pattern:** offset-based dates with a capture constant. `FIXTURE_CAPTURE_DATE = date(2026, 4, 24)`. All dates stored as integer day offsets from capture. Helper function `_offset_to_date(offset_days)` materializes to absolute date. This makes fixtures survive calendar drift.

**Six fixtures required.** Data comes from the extraction script run on 2026-04-24. Use these production values exactly:

1. `DRIFT_COVERAGE` — three matched entities:
   - `dex_pool_data`: live=True, multiple_daily, earliest 2026-04-12 (offset -12), latest 2026-04-24 (offset 0), 5 unique_days, days_since_last_record=0, coverage_window_days=12
   - `web_research_protocol`: live=False, single, earliest and latest 2026-04-13 (offset -11), 1 unique_day, days_since_last_record=11, coverage_window_days=0
   - `psi` (from historical_protocol_data): backfilled, daily, earliest 2021-12-04 (absolute date, no offset), latest 2026-04-03 (offset -21), 1582 unique_days, days_since_last_record=21, coverage_window_days=1581, data_source="historical_protocol_data"
   - adjacent_indexes_not_covering: bri, bridge_monitor, cxri, dohi, exchange_health, lsti, sii, tti, vsri, web_research_bridge, web_research_exchange
   - coverage_quality: "partial-live"
   - blocks_incident_page: True
   - blocks_reasons: mention PSI backfill not sufficient for pinned evidence per V9.6
   - recommended_analysis_types: retrospective_internal, case_study, internal_memo

2. `KELP_RSETH_COVERAGE` — one matched entity:
   - `lsti`: live=True, daily, earliest 2025-04-22 (offset -367), latest 2026-04-24 (offset 0), 368 unique_days, days_since_last_record=0, coverage_window_days=367
   - coverage_quality: "partial-live"
   - blocks_incident_page: False (LSTI is live with deep history)
   - recommended_analysis_types: all six types

3. `USDC_COVERAGE` — one matched entity:
   - `sii`: live=False (latest is 2 days stale), daily, earliest 2026-02-10 (offset -73), latest 2026-04-22 (offset -2), 72 unique_days, days_since_last_record=2, coverage_window_days=71, data_source="scores+score_history"
   - coverage_quality: "partial-live"
   - Add methodology note in blocks_reasons: USDC SII last computed 2 days ago; scheduler appears to have skipped usdc specifically on most recent run
   - blocks_incident_page: False (SII coverage is deep and only mildly stale)

4. `JUPITER_PERP_COVERAGE` — three matched entities:
   - `dex_pool_data`: live=True, multiple_daily, same shape as Drift's dex_pool_data but for jupiter-perpetual-exchange, 5 unique_days, days_since_last_record=0, coverage_window_days=12
   - `web_research_protocol`: live=False, single, same shape as Drift's, days_since_last_record=11
   - `psi` (backfilled): earliest 2024-01-29 (absolute), latest 2026-04-03 (offset -21), 796 unique_days, coverage_window_days=795
   - coverage_quality: "partial-live"
   - blocks_incident_page: True (same reason as Drift)

5. `LAYERZERO_COVERAGE` — two matched entities:
   - `bri`: live=True, daily, earliest 2025-04-22 (offset -367), latest 2026-04-24 (offset 0), 368 unique_days, days_since_last_record=0, coverage_window_days=367
   - `web_research_bridge`: live=False, single, earliest and latest 2026-04-12 (offset -12), 1 unique_day, days_since_last_record=12, coverage_window_days=0
   - coverage_quality: "partial-live"
   - blocks_incident_page: False (BRI is live with 368 days)

6. `UNKNOWN_ENTITY_COVERAGE = None` — represents a 404 response. Component 1 returns HTTP 404 for this entity; the fixture encodes the expected "no match" shape.

Every fixture must include:
- `data_snapshot_hash`: placeholder like `"sha256:drift_2026_04_24"` — Component 1 computes real hashes from live data
- `computed_at`: `FIXTURE_CAPTURE_DATETIME` (14:00 UTC on capture date)
- `related_entities: []` — v1 does not auto-populate; operator supplies peer_set explicitly
- `available_endpoints`: minimal accurate list per index (see CLAUDE.md or existing routes for real paths)

Export all six fixtures as module-level names. Also export `FIXTURE_CAPTURE_DATE`, `FIXTURE_CAPTURE_DATETIME`, and the `_offset_to_date` / `_offset_to_datetime` helpers.

Module docstring must include:
- Purpose
- Source (extraction on 2026-04-24)
- Warning: DO NOT regenerate casually; regeneration invalidates tests across parallel sessions
- Reference to Step 0 document

---

**DELIVERABLE 3: Patched SQL extraction file**

Edit `docs/analytic_engine_coverage_extraction.sql`. Locate Query 5 (the "Adjacent-index negative space" section). Replace its header comment with:

```
-- ----------------------------------------------------------------------------
-- Query 5 / 5  —  Adjacent-index negative space  [KNOWN BUG — PRESERVED FOR REFERENCE]
--
-- The UNION structure in the `covering` CTE does not correctly aggregate
-- multi-index coverage. For entities with coverage in multiple indexes
-- (e.g., drift in dex_pool_data AND web_research_protocol), this query
-- returns only one index as `covers_entity=t` and falsely marks the other
-- as `covers_entity=f`.
--
-- Component 1's real implementation computes adjacent_indexes_not_covering
-- via set difference in Python (full index universe minus indexes returned
-- by Q1+Q2+Q3). This query is preserved here as a reference only and is
-- NOT used in the canonical fixture extraction.
--
-- Do not debug or rely on this query's output. Fix is in Component 1.
-- ----------------------------------------------------------------------------
```

Leave the query body unchanged. The comment is the patch.

---

**DELIVERABLE 4: USDC follow-up note in Step 0 doc**

Append to the Step 0 document in a new section titled "Engineering Follow-ups (Standing)":

```
### USDC SII Collector Staleness
- **Observed:** 2026-04-24, during canonical fixture extraction
- **Finding:** USDC SII score last computed 2026-04-22 at 11:22 UTC, 2+ days stale. Other stablecoins (rlusd, pyusd, ousd, mim, gho, etc.) computed 2026-04-24 at 02:xx UTC.
- **Impact:** USDC's `live=False` in fixtures reflects actual DB state, not methodology. Not blocking for engine build.
- **Follow-up:** Investigate why USDC specifically is skipped in the SII collector. Priority: medium. Not engine-related; file as a separate issue.
```

---

**VERIFICATION BEFORE COMMIT**

1. `pytest tests/fixtures/` — the fixtures file must at minimum import cleanly and construct all six CoverageResponse objects without validation errors. Write a minimal `tests/fixtures/test_canonical_coverage_imports.py` that imports every fixture and calls `.model_dump()` on each to verify Pydantic validation passes.

2. `python -c "from app.engine.schemas import EntityCoverage, CoverageResponse; print('ok')"` — schema file imports without errors.

3. `grep -c "KNOWN BUG" docs/analytic_engine_coverage_extraction.sql` — returns 1.

4. Markdown document version bumped to v0.3, changelog entry present.

---

**REPORT BACK**

1. Commit SHA
2. Output of all four verification commands above
3. `cat tests/fixtures/canonical_coverage.py | head -40` — first 40 lines so operator can sanity-check the module docstring and imports
4. Any Pydantic validation errors encountered and how they were resolved
5. Confirmation that no other engine files were created (no handlers, no routers, no migrations)

---

**DO NOT**

- Do not create migrations in this commit
- Do not create routers or handlers
- Do not run production DB queries — the data is in this prompt already
- Do not modify the original extraction queries (Q1-Q4); only Query 5 gets the comment patch
- Do not regenerate fixtures by running the SQL — the values in this prompt are canonical for this capture date
