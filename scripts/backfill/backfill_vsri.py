"""
VSRI Backfill — historical Vault/Yield Strategy Risk Index scores.
Sources: DeFiLlama Yields API (APY, TVL per pool), DeFiLlama Protocol API (fallback TVL).

For each vault entity in VAULT_ENTITIES, fetches historical APY and TVL
from DeFiLlama yields (if pool_id available) or protocol-level TVL,
computes 30-day APY volatility, and writes raw_values into
generic_index_scores with backfilled=TRUE.
"""
import asyncio
import json
import logging
import math
import sys
import os
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from scripts.backfill.base import init_db, log_run_start, log_run_complete, parse_args
from app.index_definitions.vsri_v01 import VAULT_ENTITIES, VSRI_V01_DEFINITION
from app.scoring_engine import score_entity
from app.api_usage_tracker import track_api_call

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("backfill_vsri")

INDEX_ID = "vsri"
FORMULA_VERSION = "vsri-v0.2.0-backfill"
BACKFILL_SOURCE = "defillama_yields"

DEFILLAMA_YIELDS_BASE = "https://yields.llama.fi"
DEFILLAMA_BASE = "https://api.llama.fi"

# Rate-limit delay (seconds)
DL_DELAY = 0.5


async def fetch_yields_chart(client, pool_id: str) -> list | None:
    """Fetch DeFiLlama yield history for a pool. Returns data array or None."""
    path = f"/chart/{pool_id}"
    url = f"{DEFILLAMA_YIELDS_BASE}{path}"
    _t0 = time.monotonic()
    _status = None
    try:
        resp = await client.get(url)
        _status = resp.status_code
        if resp.status_code == 429:
            logger.warning(f"DeFiLlama yields rate limited on {pool_id}, sleeping 10s")
            await asyncio.sleep(10)
            return None
        if resp.status_code != 200:
            logger.warning(f"DeFiLlama yields {pool_id}: HTTP {resp.status_code}")
            return None
        body = resp.json()
        return body.get("data", body) if isinstance(body, dict) else body
    except Exception as e:
        _status = 0
        logger.error(f"DeFiLlama yields {pool_id} request failed: {e}")
        return None
    finally:
        try:
            track_api_call(provider="defillama", endpoint=path, caller="backfill.backfill_vsri", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


async def fetch_protocol_tvl(client, protocol_slug: str) -> dict | None:
    """Fetch DeFiLlama protocol data (TVL history fallback)."""
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
            track_api_call(provider="defillama", endpoint=path, caller="backfill.backfill_vsri", status=_status, latency_ms=int((time.monotonic() - _t0) * 1000))
        except Exception:
            pass


def build_yields_maps(data: list) -> tuple[dict, dict]:
    """Parse DeFiLlama yields data into date-keyed APY and TVL maps.
    Returns (apy_map, tvl_map) as {date_str: value}."""
    apy_map = {}
    tvl_map = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ts = entry.get("timestamp")
        if ts is None:
            continue
        try:
            # timestamp can be ISO string or epoch
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            else:
                dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            date_key = dt.strftime("%Y-%m-%d")
        except (ValueError, OSError, TypeError):
            continue
        apy = entry.get("apy")
        tvl = entry.get("tvlUsd")
        if apy is not None:
            apy_map[date_key] = float(apy)
        if tvl is not None:
            tvl_map[date_key] = float(tvl)
    return apy_map, tvl_map


def build_protocol_tvl_map(tvl_array: list) -> dict:
    """Convert DeFiLlama protocol TVL array to {date_str: tvl}."""
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


def compute_apy_volatility_30d(apy_map: dict, target_date: str) -> float | None:
    """Compute trailing 30-day APY standard deviation ending on target_date."""
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    values = []
    for i in range(30):
        d = (target - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in apy_map:
            values.append(apy_map[d])
    if len(values) < 5:
        return None
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return round(math.sqrt(variance), 4)


async def backfill_entity(entity: dict, days_back: int = 365):
    """Backfill a single vault entity from DeFiLlama data."""
    import httpx
    from app.database import execute

    slug = entity["slug"]
    name = entity["name"]
    protocol = entity.get("protocol", "")
    pool_id = entity.get("pool_id")

    run_id = log_run_start(INDEX_ID, slug, BACKFILL_SOURCE)
    rows_written = 0
    rows_failed = 0

    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    logger.info(f"VSRI backfill {slug}: {start_date.date()} -> {end_date.date()}")

    apy_map = {}
    tvl_map = {}

    async with httpx.AsyncClient(timeout=30) as client:
        if pool_id:
            # Fetch yields history from DeFiLlama yields API
            data = await fetch_yields_chart(client, pool_id)
            await asyncio.sleep(DL_DELAY)
            if data:
                apy_map, tvl_map = build_yields_maps(data)
        else:
            # Fallback: fetch protocol-level TVL
            if protocol:
                dl_data = await fetch_protocol_tvl(client, protocol)
                await asyncio.sleep(DL_DELAY)
                if dl_data:
                    tvl_map = build_protocol_tvl_map(dl_data.get("tvl", []))

    if not apy_map and not tvl_map:
        logger.info(f"VSRI backfill {slug}: no historical data found")
        log_run_complete(run_id, 0, 0, "no_data")
        return 0, 0

    # Generate daily rows
    current = start_date
    while current <= end_date:
        score_date = current.date()
        date_key = score_date.strftime("%Y-%m-%d")

        apy = apy_map.get(date_key)
        tvl = tvl_map.get(date_key)
        apy_vol = compute_apy_volatility_30d(apy_map, date_key)

        raw_values = {}
        if apy is not None:
            raw_values["apy"] = round(apy, 4)
        if tvl is not None:
            raw_values["tvl"] = round(tvl, 2)
        if apy_vol is not None:
            raw_values["apy_volatility_30d"] = apy_vol

        # Skip dates with no data at all
        if not raw_values:
            current += timedelta(days=1)
            continue

        # Dispatch through V9.9 aggregation registry. Mirrors live scoring
        # path (vault_collector.score_vault → score_entity → aggregate()).
        # VSRI v0.2 uses coverage_withheld; below threshold returns
        # overall_score=None and withheld=True.
        result = score_entity(VSRI_V01_DEFINITION, raw_values)

        try:
            execute(
                """
                INSERT INTO generic_index_scores
                    (index_id, entity_slug, entity_name, overall_score, raw_values,
                     component_scores, category_scores,
                     formula_version, scored_date, backfilled, backfill_source,
                     coverage, component_coverage, components_populated, components_total,
                     missing_categories, aggregation_method, aggregation_formula_version,
                     effective_category_weights, withheld,
                     confidence, confidence_tag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                 json.dumps(result["effective_category_weights"]),
                 result["withheld"],
                 result["confidence"], result["confidence_tag"]),
            )
            rows_written += 1
        except Exception as e:
            rows_failed += 1
            if rows_failed <= 3:
                logger.warning(f"VSRI backfill row {slug}/{score_date}: {e}")

        current += timedelta(days=1)

    logger.info(f"VSRI backfill {slug}: {rows_written} written, {rows_failed} failed")
    log_run_complete(run_id, rows_written, rows_failed)
    return rows_written, rows_failed


async def main():
    args = parse_args()
    init_db()

    entities = VAULT_ENTITIES
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
                f"VSRI progress: {i + 1}/{len(entities)} entities, "
                f"{total_written} total rows written, {total_failed} failed"
            )

    logger.info(
        f"VSRI backfill complete: {len(entities)} entities, "
        f"{total_written} rows written, {total_failed} failed"
    )


if __name__ == "__main__":
    asyncio.run(main())
