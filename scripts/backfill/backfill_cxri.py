"""
CXRI Backfill — historical CEX Reserve Integrity Index scores.
Sources: CoinGecko Exchanges API (trust_score, volume, volume chart).

For each exchange in CEX_ENTITIES, fetches current exchange data and
historical volume chart from CoinGecko, then writes raw_values into
generic_index_scores with backfilled=TRUE.
"""
import asyncio
import json
import logging
import sys
import os
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scripts.backfill.base import init_db, log_run_start, log_run_complete, parse_args
from app.index_definitions.cxri_v01 import CEX_ENTITIES, CXRI_V01_DEFINITION
from app.scoring_engine import score_entity
from app.api_usage_tracker import track_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_cxri")

INDEX_ID = "cxri"
FORMULA_VERSION = "cxri-v0.2.0-backfill"
BACKFILL_SOURCE = "coingecko_exchanges"

COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")
CG_BASE = "https://pro-api.coingecko.com/api/v3" if COINGECKO_API_KEY else "https://api.coingecko.com/api/v3"
CG_HEADERS = {"x-cg-pro-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

# Rate-limit delay (seconds)
CG_DELAY = 2.0


async def fetch_exchange_info(client, coingecko_id: str) -> dict | None:
    """Fetch CoinGecko exchange data (trust_score, volume, tickers)."""
    path = f"/exchanges/{coingecko_id}"
    url = f"{CG_BASE}{path}"
    _t0 = time.monotonic()
    _status = None
    try:
        resp = await client.get(url, headers=CG_HEADERS)
        _status = resp.status_code
        if resp.status_code == 429:
            logger.warning(f"CoinGecko rate limited on {coingecko_id}, sleeping 10s")
            await asyncio.sleep(10)
            return None
        if resp.status_code != 200:
            logger.warning(f"CoinGecko exchange {coingecko_id}: HTTP {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        _status = 0
        logger.error(f"CoinGecko exchange {coingecko_id} request failed: {e}")
        return None
    finally:
        try:
            track_api_call(provider="coingecko", endpoint=path, caller="backfill.backfill_cxri", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


async def fetch_volume_chart_range(client, coingecko_id: str, start_ts: int, end_ts: int) -> list | None:
    """Fetch CoinGecko exchange volume chart for a date range.
    Returns list of [timestamp_ms, volume_str] or None."""
    path = f"/exchanges/{coingecko_id}/volume_chart/range"
    url = f"{CG_BASE}{path}?from={start_ts}&to={end_ts}"
    _t0 = time.monotonic()
    _status = None
    try:
        resp = await client.get(url, headers=CG_HEADERS)
        _status = resp.status_code
        if resp.status_code == 429:
            logger.warning(f"CoinGecko volume chart rate limited on {coingecko_id}, sleeping 10s")
            await asyncio.sleep(10)
            return None
        if resp.status_code != 200:
            logger.warning(f"CoinGecko volume chart {coingecko_id}: HTTP {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        _status = 0
        logger.error(f"CoinGecko volume chart {coingecko_id} request failed: {e}")
        return None
    finally:
        try:
            track_api_call(provider="coingecko", endpoint=path, caller="backfill.backfill_cxri", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


def build_volume_map(volume_data: list) -> dict:
    """Convert [[timestamp_ms, volume_str], ...] to {date_str: volume_float}."""
    result = {}
    for entry in volume_data:
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        ts_ms, vol = entry[0], entry[1]
        try:
            dt = datetime.fromtimestamp(float(ts_ms) / 1000, tz=timezone.utc)
            result[dt.strftime("%Y-%m-%d")] = float(vol)
        except (ValueError, OSError, TypeError):
            continue
    return result


async def backfill_entity(entity: dict, days_back: int = 365):
    """Backfill a single CEX entity from CoinGecko data."""
    import httpx
    from app.database import execute

    slug = entity["slug"]
    name = entity["name"]
    coingecko_id = entity.get("coingecko_id")

    if not coingecko_id:
        logger.warning(f"CXRI backfill {slug}: no coingecko_id, skipping")
        return 0, 0

    run_id = log_run_start(INDEX_ID, slug, BACKFILL_SOURCE)
    rows_written = 0
    rows_failed = 0

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    logger.info(f"CXRI backfill {slug}: {start_date.date()} -> {end_date.date()}")

    trust_score = None
    trust_score_rank = None
    trade_volume_24h_btc = None
    num_tickers = None
    volume_map = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch current exchange info (trust_score is static/current)
        info = await fetch_exchange_info(client, coingecko_id)
        await asyncio.sleep(CG_DELAY)

        if info:
            trust_score = info.get("trust_score")
            trust_score_rank = info.get("trust_score_rank")
            trade_volume_24h_btc = info.get("trade_volume_24h_btc")
            tickers = info.get("tickers", [])
            num_tickers = len(tickers) if isinstance(tickers, list) else None

        # Fetch volume chart in 90-day windows
        window_start = start_date
        while window_start < end_date:
            window_end = min(window_start + timedelta(days=90), end_date)
            start_ts = int(window_start.timestamp())
            end_ts = int(window_end.timestamp())

            vol_data = await fetch_volume_chart_range(client, coingecko_id, start_ts, end_ts)
            await asyncio.sleep(CG_DELAY)

            if vol_data:
                volume_map.update(build_volume_map(vol_data))

            window_start = window_end

    if not volume_map and trust_score is None:
        logger.info(f"CXRI backfill {slug}: no historical data found")
        log_run_complete(run_id, 0, 0, "no_data")
        return 0, 0

    # Generate daily rows
    current = start_date
    while current <= end_date:
        score_date = current.date()
        date_key = score_date.strftime("%Y-%m-%d")

        daily_volume = volume_map.get(date_key)

        raw_values = {}
        if daily_volume is not None:
            raw_values["trade_volume_24h"] = round(daily_volume, 2)
        # Trust score: use current value (CoinGecko doesn't provide historical)
        if trust_score is not None:
            raw_values["trust_score"] = trust_score
        if trust_score_rank is not None:
            raw_values["trust_score_rank"] = trust_score_rank
        if num_tickers is not None:
            raw_values["num_tickers"] = num_tickers

        # Skip dates with no data at all
        if not raw_values:
            current += timedelta(days=1)
            continue

        # Dispatch through V9.9 aggregation registry. Mirrors live scoring
        # path (cex_collector.score_cex → score_entity → aggregate()).
        result = score_entity(CXRI_V01_DEFINITION, raw_values)

        try:
            execute(
                """
                INSERT INTO generic_index_scores
                    (index_id, entity_slug, entity_name, overall_score, raw_values,
                     component_scores, category_scores,
                     formula_version, scored_date, backfilled, backfill_source,
                     coverage, component_coverage, components_populated, components_total,
                     missing_categories, aggregation_method, aggregation_formula_version,
                     aggregation_params, effective_category_weights, withheld,
                     confidence, confidence_tag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (index_id, entity_slug, scored_date) DO UPDATE SET
                    overall_score = EXCLUDED.overall_score,
                    raw_values = EXCLUDED.raw_values,
                    component_scores = EXCLUDED.component_scores,
                    category_scores = EXCLUDED.category_scores,
                    backfill_source = EXCLUDED.backfill_source,
                    coverage = EXCLUDED.coverage,
                    component_coverage = EXCLUDED.component_coverage,
                    components_populated = EXCLUDED.components_populated,
                    components_total = EXCLUDED.components_total,
                    missing_categories = EXCLUDED.missing_categories,
                    aggregation_method = EXCLUDED.aggregation_method,
                    aggregation_formula_version = EXCLUDED.aggregation_formula_version,
                    aggregation_params = EXCLUDED.aggregation_params,
                    effective_category_weights = EXCLUDED.effective_category_weights,
                    withheld = EXCLUDED.withheld,
                    confidence = EXCLUDED.confidence,
                    confidence_tag = EXCLUDED.confidence_tag
                """,
                (INDEX_ID, slug, name, result["overall_score"],
                 json.dumps(raw_values),
                 json.dumps(result["component_scores"]),
                 json.dumps(result["category_scores"]),
                 FORMULA_VERSION, score_date, BACKFILL_SOURCE,
                 result["coverage"], result["component_coverage"],
                 result["components_populated"], result["components_total"],
                 json.dumps(result["missing_categories"]),
                 result["aggregation_method"], result["aggregation_formula_version"],
                 json.dumps(CXRI_V01_DEFINITION.get("aggregation", {}).get("params", {})),
                 json.dumps(result["effective_category_weights"]),
                 result["withheld"],
                 result["confidence"], result["confidence_tag"]),
            )
            rows_written += 1
        except Exception as e:
            rows_failed += 1
            if rows_failed <= 3:
                logger.warning(f"CXRI backfill row {slug}/{score_date}: {e}")

        current += timedelta(days=1)

    logger.info(f"CXRI backfill {slug}: {rows_written} written, {rows_failed} failed")
    log_run_complete(run_id, rows_written, rows_failed)
    return rows_written, rows_failed


async def main():
    args = parse_args()
    init_db()

    entities = CEX_ENTITIES
    if args.limit > 0:
        entities = entities[: args.limit]

    total_written = 0
    total_failed = 0

    for i, entity in enumerate(entities):
        written, failed = await backfill_entity(entity, days_back=args.days_back)
        total_written += written
        total_failed += failed

        if (i + 1) % 4 == 0 or (i + 1) == len(entities):
            logger.info(
                f"CXRI progress: {i + 1}/{len(entities)} entities, "
                f"{total_written} total rows written, {total_failed} failed"
            )

    logger.info(
        f"CXRI backfill complete: {len(entities)} entities, "
        f"{total_written} rows written, {total_failed} failed"
    )


if __name__ == "__main__":
    asyncio.run(main())
