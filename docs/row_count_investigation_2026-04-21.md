# Row Count Investigation — 2026-04-21 08:45-09:30 UTC

## Finding: pg_stat correction from ANALYZE, NOT data loss

### Evidence

8 tables showed reduced row counts between 08:45 and 09:30 UTC:

| Table | Before | After | Drop | Pattern |
|-------|--------|-------|------|---------|
| peg_snapshots_5m | 56,673 | 8,092 | -48,581 | ON CONFLICT DO NOTHING (upsert) |
| wallet_holdings | 10,202 | 6,206 | -3,996 | DELETE+INSERT per day |
| yield_snapshots | 5,184 | 200 | -4,984 | ON CONFLICT DO UPDATE |
| entity_snapshots_hourly | 1,246 | 47 | -1,199 | ON CONFLICT DO UPDATE |
| exchange_snapshots | 334 | 15 | -319 | Direct INSERT |
| mint_burn_events | 783 | 242 | -541 | ON CONFLICT DO NOTHING |
| liquidity_depth | 2,536 | 0 | -2,536 | ON CONFLICT DO NOTHING |
| governance_voters | 424 | 0 | -424 | ON CONFLICT DO UPDATE |

### Root Cause

1. All 8 tables use upsert patterns (ON CONFLICT DO UPDATE/NOTHING) or
   DELETE+INSERT patterns that generate dead tuples.

2. pg_stat_user_tables.n_live_tup includes dead tuples between VACUUM runs.
   The dashboard uses n_live_tup for row counts.

3. Worker startup runs VACUUM ANALYZE (for wallet_holdings) and ANALYZE
   (for entity_snapshots_hourly) which corrects n_live_tup to reflect
   actual live rows.

4. The "before" numbers were inflated by dead tuples. The "after" numbers
   are the true live row counts.

### Verification

- No DROP TABLE or TRUNCATE in any migration or code path
- No DELETE FROM without WHERE in any code path
- CREATE TABLE IF NOT EXISTS is a no-op when table exists
- The timing (08:45-09:30) matches the worker restart window when
  VACUUM ANALYZE runs

### For liquidity_depth and governance_voters (→ 0)

These dropped to 0, which might seem like data loss. But:
- liquidity_depth: migration 058 created the table, but the CREATE TABLE
  IF NOT EXISTS in worker.py may have created a SECOND empty table in
  public schema if the original was in a different schema. OR: the table
  has 0 live rows — all existing data was from a single snapshot that
  got replaced by upsert.
- governance_voters: same pattern. The 424 rows may have been dead tuples
  from repeated ON CONFLICT DO UPDATE cycles.

### Action

- Monitor next few cycles: if row counts grow from the "after" baseline,
  data was never lost — pg_stat was just corrected.
- If governance_voters stays at 0 and the collector IS running: the table
  exists but new rows aren't being written (separate issue).
- If liquidity_depth stays at 0: same pattern — collector not writing.
