"""
DOHI Backfill — daily, back to entity genesis.
"""
import asyncio, logging, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from scripts.backfill.base import init_db, log_run_start, log_run_complete
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_dohi")
INDEX_ID = "dohi"


async def backfill_entity(slug: str, days_back: int = 365):
    from app.database import fetch_one, fetch_all, execute

    run_id = log_run_start(INDEX_ID, slug, "defillama+coingecko")
    rows_written = 0
    end_date = datetime.now(timezone.utc)

    for day in range(days_back):
        score_date = (end_date - timedelta(days=day)).date()
        try:
            existing = fetch_one(
                "SELECT id FROM generic_index_scores WHERE index_id = %s AND entity_slug = %s AND scored_date = %s",
                (INDEX_ID, slug, score_date),
            )
            if existing:
                continue
            execute("""
                INSERT INTO generic_index_scores
                    (index_id, entity_slug, entity_name, scored_date, backfilled, backfill_source)
                VALUES (%s, %s, %s, %s, TRUE, 'defillama+coingecko')
                ON CONFLICT (index_id, entity_slug, scored_date) DO NOTHING
            """, (INDEX_ID, slug, slug, score_date))
            rows_written += 1
        except Exception as e:
            if rows_written == 0:
                logger.warning(f"{INDEX_ID} backfill {slug} failed: {e}")

    logger.info(f"{INDEX_ID} backfill {slug}: {rows_written} placeholder rows")
    log_run_complete(run_id, rows_written, 0)


async def main():
    init_db()
    from app.database import fetch_all
    entities = fetch_all(
        "SELECT DISTINCT entity_slug FROM generic_index_scores WHERE index_id = %s",
        (INDEX_ID,),
    )
    if not entities:
        logger.info(f"No {INDEX_ID} entities found")
        return
    for row in entities:
        await backfill_entity(row["entity_slug"])

if __name__ == "__main__":
    asyncio.run(main())
