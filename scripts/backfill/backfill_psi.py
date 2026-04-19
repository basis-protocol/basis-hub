"""
PSI Backfill — daily, back to protocol deployment.
Sources: DeFiLlama (TVL, fees), Snapshot (governance), Blockscout (contracts).
"""
import asyncio
import logging
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scripts.backfill.base import init_db, log_run_start, log_run_complete, date_range
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_psi")

PROTOCOLS = [
    "aave", "compound-finance", "morpho", "spark", "lido",
    "uniswap", "curve-finance", "convex-finance", "eigenlayer",
    "sky", "pendle", "ethena", "drift",
]


async def backfill_protocol(slug: str, days_back: int = 365):
    from app.database import fetch_one, execute
    import httpx

    run_id = log_run_start("psi", slug, "defillama+snapshot")
    rows_written = 0
    rows_failed = 0
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    logger.info(f"PSI backfill {slug}: {start_date.date()} → {end_date.date()}")

    try:
        # Fetch historical TVL from DeFiLlama
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"https://api.llama.fi/protocol/{slug}")
            if resp.status_code != 200:
                logger.warning(f"DeFiLlama {slug}: {resp.status_code}")
                log_run_complete(run_id, 0, 0, f"DeFiLlama {resp.status_code}")
                return
            data = resp.json()

        tvl_history = data.get("tvl", [])
        if not tvl_history:
            logger.info(f"PSI backfill {slug}: no TVL history")
            log_run_complete(run_id, 0, 0, "no TVL history")
            return

        for point in tvl_history:
            try:
                ts = datetime.fromtimestamp(point["date"], tz=timezone.utc)
                if ts < start_date or ts > end_date:
                    continue
                tvl = float(point.get("totalLiquidityUSD", 0))
                score_date = ts.date()

                # Check if already exists
                existing = fetch_one(
                    "SELECT id FROM psi_scores WHERE protocol_slug = %s AND scored_date = %s",
                    (slug, score_date),
                )
                if existing:
                    continue

                execute("""
                    INSERT INTO psi_scores
                        (protocol_slug, protocol_name, overall_score, raw_values,
                         formula_version, scored_date, backfilled, backfill_source)
                    VALUES (%s, %s, NULL, %s, 'psi-v0.2.0-backfill', %s, TRUE, 'defillama')
                    ON CONFLICT (protocol_slug, scored_date) DO NOTHING
                """, (slug, slug, f'{{"tvl": {tvl}}}', score_date))
                rows_written += 1
            except Exception as e:
                rows_failed += 1
                if rows_failed <= 3:
                    logger.warning(f"PSI backfill row failed {slug}: {e}")

    except Exception as e:
        logger.error(f"PSI backfill {slug} failed: {e}")
        log_run_complete(run_id, rows_written, rows_failed, str(e))
        return

    logger.info(f"PSI backfill {slug}: {rows_written} written, {rows_failed} failed")
    log_run_complete(run_id, rows_written, rows_failed)


async def main():
    init_db()
    for slug in PROTOCOLS:
        await backfill_protocol(slug)


if __name__ == "__main__":
    asyncio.run(main())
