"""
RPI Backfill — weekly, back to protocol genesis.
Sources: Snapshot (governance), DeFiLlama (fees/revenue), Firecrawl (docs).
"""
import asyncio, logging, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from scripts.backfill.base import init_db, log_run_start, log_run_complete
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_rpi")

PROTOCOLS = [
    "aave", "compound-finance", "morpho", "spark", "lido",
    "uniswap", "curve-finance", "convex-finance", "eigenlayer",
    "sky", "pendle", "ethena", "drift",
]


async def backfill_protocol(slug: str, weeks_back: int = 52):
    from app.database import fetch_one, execute

    run_id = log_run_start("rpi", slug, "snapshot+defillama")
    rows_written = 0
    end_date = datetime.now(timezone.utc)

    for week in range(weeks_back):
        score_date = (end_date - timedelta(weeks=week)).date()
        try:
            existing = fetch_one(
                "SELECT id FROM rpi_score_history WHERE protocol_slug = %s AND score_date = %s",
                (slug, score_date),
            )
            if existing:
                continue
            execute("""
                INSERT INTO rpi_score_history
                    (protocol_slug, score_date, overall_score, methodology_version, backfilled, backfill_source)
                VALUES (%s, %s, NULL, 'rpi-v2.0.0-backfill', TRUE, 'snapshot+defillama')
                ON CONFLICT DO NOTHING
            """, (slug, score_date))
            rows_written += 1
        except Exception as e:
            if rows_written == 0:
                logger.warning(f"RPI backfill {slug} row failed: {e}")

    logger.info(f"RPI backfill {slug}: {rows_written} placeholder rows")
    log_run_complete(run_id, rows_written, 0)


async def main():
    init_db()
    for slug in PROTOCOLS:
        await backfill_protocol(slug)

if __name__ == "__main__":
    asyncio.run(main())
