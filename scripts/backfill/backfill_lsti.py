"""
LSTI Backfill — historical Liquid Staking Token Integrity Index scores.
Sources: CoinGecko (price, market_cap, volume), DeFiLlama (TVL).

For each LST entity in LST_ENTITIES, fetches historical price/volume from
CoinGecko (90-day windows) and TVL from DeFiLlama, computes peg_deviation
relative to ETH price, and writes raw_values into generic_index_scores
with backfilled=TRUE.
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
from app.index_definitions.lsti_v01 import LST_ENTITIES
from app.api_usage_tracker import track_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_lsti")

INDEX_ID = "lsti"
FORMULA_VERSION = "lsti-v0.1.0-backfill"
BACKFILL_SOURCE = "coingecko+defillama"

COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")
CG_BASE = "https://pro-api.coingecko.com/api/v3" if COINGECKO_API_KEY else "https://api.coingecko.com/api/v3"
CG_HEADERS = {"x-cg-pro-api-key": COINGECKO_API_KEY} if COINGECKO_API_KEY else {}

DEFILLAMA_BASE = "https://api.llama.fi"

# Rate-limit delays (seconds)
CG_DELAY = 2.0
DL_DELAY = 0.5


async def fetch_coingecko_market_chart(client, coingecko_id: str, start_ts: int, end_ts: int) -> dict | None:
    """Fetch CoinGecko market_chart/range for a coin. Returns parsed JSON or None."""
    path = f"/coins/{coingecko_id}/market_chart/range"
    url = f"{CG_BASE}{path}?vs_currency=usd&from={start_ts}&to={end_ts}"
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
            logger.warning(f"CoinGecko {coingecko_id}: HTTP {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        _status = 0
        logger.error(f"CoinGecko {coingecko_id} request failed: {e}")
        return None
    finally:
        try:
            track_api_call(provider="coingecko", endpoint=path, caller="backfill.backfill_lsti", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


async def fetch_defillama_protocol(client, protocol_slug: str) -> dict | None:
    """Fetch DeFiLlama protocol data (includes TVL history)."""
    path = f"/protocol/{protocol_slug}"
    url = f"{DEFILLAMA_BASE}{path}"
    _t0 = time.monotonic()
    _status = None
    try:
        resp = await client.get(url)
        _status = resp.status_code
        if resp.status_code == 429:
            logger.warning(f"DeFiLlama rate limited on {protocol_slug}, sleeping 10s")
            await asyncio.sleep(10)
            return None
        if resp.status_code != 200:
            logger.warning(f"DeFiLlama {protocol_slug}: HTTP {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        _status = 0
        logger.error(f"DeFiLlama {protocol_slug} request failed: {e}")
        return None
    finally:
        try:
            track_api_call(provider="defillama", endpoint=path, caller="backfill.backfill_lsti", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


def build_date_map(timeseries: list) -> dict:
    """Convert [[timestamp_ms, value], ...] to {date_str: value}."""
    result = {}
    for ts_ms, val in timeseries:
        try:
            dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            result[dt.strftime("%Y-%m-%d")] = val
        except (ValueError, OSError, TypeError):
            continue
    return result


def build_tvl_map(tvl_array: list) -> dict:
    """Convert DeFiLlama [{date: epoch, totalLiquidityUSD: val}, ...] to {date_str: val}."""
    result = {}
    for entry in tvl_array:
        ts = entry.get("date")
        tvl = entry.get("totalLiquidityUSD", 0) or 0
        if ts is None:
            continue
        try:
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            result[dt.strftime("%Y-%m-%d")] = float(tvl)
        except (ValueError, OSError, TypeError):
            continue
    return result


def interpolate_nearest(date_map: dict, target_date: str) -> float | None:
    """Return value for target_date, or nearest date within 3 days."""
    if target_date in date_map:
        return date_map[target_date]
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    best_val = None
    best_dist = 4  # only search within 3 days
    for date_str, val in date_map.items():
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            dist = abs((d - target).days)
            if dist < best_dist:
                best_dist = dist
                best_val = val
        except ValueError:
            continue
    return best_val


async def backfill_entity(entity: dict, days_back: int = 365):
    """Backfill a single LST entity from CoinGecko + DeFiLlama data."""
    import httpx
    from app.database import execute

    slug = entity["slug"]
    name = entity["name"]
    coingecko_id = entity.get("coingecko_id")
    protocol_slug = entity.get("protocol", "").lower().replace(" ", "-")

    if not coingecko_id:
        logger.warning(f"LSTI backfill {slug}: no coingecko_id, skipping")
        return 0, 0

    run_id = log_run_start(INDEX_ID, slug, BACKFILL_SOURCE)
    rows_written = 0
    rows_failed = 0

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    logger.info(f"LSTI backfill {slug}: {start_date.date()} -> {end_date.date()}")

    # Collect all CoinGecko data in 90-day windows
    price_map = {}
    mcap_map = {}
    volume_map = {}
    eth_price_map = {}

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch LST data in 90-day windows
        window_start = start_date
        while window_start < end_date:
            window_end = min(window_start + timedelta(days=90), end_date)
            start_ts = int(window_start.timestamp())
            end_ts = int(window_end.timestamp())

            data = await fetch_coingecko_market_chart(client, coingecko_id, start_ts, end_ts)
            await asyncio.sleep(CG_DELAY)

            if data:
                price_map.update(build_date_map(data.get("prices", [])))
                mcap_map.update(build_date_map(data.get("market_caps", [])))
                volume_map.update(build_date_map(data.get("total_volumes", [])))

            window_start = window_end

        # Fetch ETH price data in 90-day windows (for peg deviation)
        window_start = start_date
        while window_start < end_date:
            window_end = min(window_start + timedelta(days=90), end_date)
            start_ts = int(window_start.timestamp())
            end_ts = int(window_end.timestamp())

            eth_data = await fetch_coingecko_market_chart(client, "ethereum", start_ts, end_ts)
            await asyncio.sleep(CG_DELAY)

            if eth_data:
                eth_price_map.update(build_date_map(eth_data.get("prices", [])))

            window_start = window_end

        # Fetch DeFiLlama TVL history
        tvl_map = {}
        if protocol_slug:
            dl_data = await fetch_defillama_protocol(client, protocol_slug)
            await asyncio.sleep(DL_DELAY)
            if dl_data:
                tvl_map = build_tvl_map(dl_data.get("tvl", []))

    if not price_map and not tvl_map:
        logger.info(f"LSTI backfill {slug}: no historical data found")
        log_run_complete(run_id, 0, 0, "no_data")
        return 0, 0

    # Generate daily rows
    current = start_date
    while current <= end_date:
        score_date = current.date()
        date_key = score_date.strftime("%Y-%m-%d")

        price = interpolate_nearest(price_map, date_key)
        market_cap = interpolate_nearest(mcap_map, date_key)
        volume_24h = interpolate_nearest(volume_map, date_key)
        tvl = interpolate_nearest(tvl_map, date_key)
        eth_price = interpolate_nearest(eth_price_map, date_key)

        # Compute peg deviation relative to ETH
        peg_deviation = None
        if price is not None and eth_price is not None and eth_price > 0:
            peg_deviation = round(abs(1.0 - price / eth_price), 6)

        raw_values = {}
        if price is not None:
            raw_values["price"] = round(price, 6)
        if market_cap is not None:
            raw_values["market_cap"] = round(market_cap, 2)
        if volume_24h is not None:
            raw_values["volume_24h"] = round(volume_24h, 2)
        if tvl is not None:
            raw_values["tvl"] = round(tvl, 2)
        if peg_deviation is not None:
            raw_values["peg_deviation"] = peg_deviation
        if eth_price is not None:
            raw_values["eth_price"] = round(eth_price, 2)

        # Skip dates with no data at all
        if not raw_values:
            current += timedelta(days=1)
            continue

        try:
            execute(
                """
                INSERT INTO generic_index_scores
                    (index_id, entity_slug, entity_name, overall_score, raw_values,
                     formula_version, scored_date, backfilled, backfill_source)
                VALUES (%s, %s, %s, NULL, %s, %s, %s, TRUE, %s)
                ON CONFLICT (index_id, entity_slug, scored_date) DO UPDATE SET
                    raw_values = EXCLUDED.raw_values,
                    backfill_source = EXCLUDED.backfill_source
                """,
                (INDEX_ID, slug, name, json.dumps(raw_values), FORMULA_VERSION,
                 score_date, BACKFILL_SOURCE),
            )
            rows_written += 1
        except Exception as e:
            rows_failed += 1
            if rows_failed <= 3:
                logger.warning(f"LSTI backfill row {slug}/{score_date}: {e}")

        current += timedelta(days=1)

    logger.info(f"LSTI backfill {slug}: {rows_written} written, {rows_failed} failed")
    log_run_complete(run_id, rows_written, rows_failed)
    return rows_written, rows_failed


async def main():
    args = parse_args()
    init_db()

    entities = LST_ENTITIES
    if args.limit > 0:
        entities = entities[: args.limit]

    total_written = 0
    total_failed = 0

    for i, entity in enumerate(entities):
        written, failed = await backfill_entity(entity, days_back=args.days_back)
        total_written += written
        total_failed += failed

        if (i + 1) % 5 == 0 or (i + 1) == len(entities):
            logger.info(
                f"LSTI progress: {i + 1}/{len(entities)} entities, "
                f"{total_written} total rows written, {total_failed} failed"
            )

    logger.info(
        f"LSTI backfill complete: {len(entities)} entities, "
        f"{total_written} rows written, {total_failed} failed"
    )


if __name__ == "__main__":
    asyncio.run(main())
