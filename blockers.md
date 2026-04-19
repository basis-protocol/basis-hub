# Blockers — 2026-04-19

## Railway CLI not available

The Railway CLI (`railway`) is not installed in the Claude Code environment.
Cannot execute any of the backfill launch steps (1.1-6) from this session.

### What's needed

1. Install Railway CLI on a persistent host (local machine, CI runner, or Railway shell)
2. Authenticate: `railway login`
3. Link project: `railway link`
4. Then follow the launch steps from the session prompt

### Alternative: Launch from Railway Dashboard

All three backfillers can be launched from the Railway dashboard UI:

1. Go to the basis-hub project in Railway dashboard
2. Create new service → "Empty Service" → Link to basis-hub repo
3. Set start command:
   - PSI: `python -m scripts.backfill.backfill_psi`
   - RPI: `python -m scripts.backfill.backfill_rpi`
   - LSTI: `python -m scripts.backfill.backfill_lsti`
4. Copy DATABASE_URL from existing web service
5. Deploy

### Pre-flight still needed

Before launching, migrations 077 and 078 must be applied on production.
The worker's startup code in main() runs CREATE TABLE IF NOT EXISTS for
many tables but does NOT run migration SQL files. Either:
- Apply via psql: `psql $DATABASE_URL < migrations/077_backfill_flag.sql`
- Or add the ALTER TABLE statements to worker.py startup (same pattern as oracle tables)

### Backfill scripts ready

All 8 scripts are committed and syntax-checked:
- scripts/backfill/backfill_psi.py ✅
- scripts/backfill/backfill_rpi.py ✅
- scripts/backfill/backfill_lsti.py ✅
- scripts/backfill/backfill_bri.py (deferred)
- scripts/backfill/backfill_dohi.py (deferred)
- scripts/backfill/backfill_vsri.py (deferred)
- scripts/backfill/backfill_cxri.py (deferred)
- scripts/backfill/backfill_tti.py (deferred)
