"""
GeckoTerminal OHLCV Collector
==============================
Pool-level candlestick data for market microstructure analysis.
Feeds Tier 1 liquidity depth with open/high/low/close/volume per pool.

CoinGecko Pro endpoint:
  GET /onchain/simple/networks/{network}/dex/{dex}/pools/{pool}/ohlcv/{timeframe}
  Alternative: GET /onchain/networks/{network}/pools/{pool}/ohlcv/{timeframe}

Timeframes: day, hour, minute (1m, 5m, 15m)

Estimated calls: ~200 pools × 8 cycles/day = 1,600 calls/day (~10% CG budget)

Schedule: Every slow cycle (3h)
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

API_KEY = os.environ.get("COINGECKO_API_KEY", "")
GT_BASE = "https://pro-api.coingecko.com/api/v3/onchain" if API_KEY else "https://api.coingecko.com/api/v3/onchain"

CHAIN_MAP = {
    "ethereum": "eth",
    "base": "base",
    "arbitrum": "arbitrum-one",
}


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if API_KEY:
        h["x-cg-pro-api-key"] = API_KEY
    return h


async def _fetch_pool_ohlcv(
    client: httpx.AsyncClient,
    network: str,
    pool_address: str,
    timeframe: str = "hour",
    limit: int = 24,
) -> list[dict]:
    """Fetch OHLCV data for a specific pool."""
    from app.shared_rate_limiter import rate_limiter
    from app.api_usage_tracker import track_api_call

    await rate_limiter.acquire("coingecko")

    url = f"{GT_BASE}/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}"
    params = {"limit": limit, "currency": "usd"}

    start = time.time()
    try:
        resp = await client.get(url, params=params, headers=_headers(), timeout=15)
        latency = int((time.time() - start) * 1000)
        track_api_call("coingecko", f"/onchain/pools/{pool_address[:10]}/ohlcv",
                       caller="ohlcv_collector", status=resp.status_code, latency_ms=latency)

        if resp.status_code == 429:
            rate_limiter.report_429("coingecko")
            return []

        resp.raise_for_status()
        rate_limiter.report_success("coingecko")
        data = resp.json()

        # GeckoTerminal OHLCV format: data.attributes.ohlcv_list
        attrs = data.get("data", {}).get("attributes", {})
        ohlcv_list = attrs.get("ohlcv_list", [])
        return ohlcv_list
    except Exception as e:
        latency = int((time.time() - start) * 1000)
        track_api_call("coingecko", f"/onchain/pools/{pool_address[:10]}/ohlcv",
                       caller="ohlcv_collector", status=500, latency_ms=latency)
        logger.debug(f"OHLCV fetch failed for {pool_address[:10]}… on {network}: {e}")
        return []


def _store_ohlcv_records(records: list[dict]):
    """Store OHLCV records to database."""
    if not records:
        return

    from app.database import get_cursor

    with get_cursor() as cur:
        for rec in records:
            cur.execute(
                """INSERT INTO dex_pool_ohlcv
                   (pool_address, chain, dex, asset_id, timestamp,
                    open, high, low, close, volume, trades_count)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (pool_address, chain, timestamp) DO UPDATE SET
                       volume = EXCLUDED.volume,
                       close = EXCLUDED.close""",
                (
                    rec["pool_address"], rec["chain"], rec.get("dex"),
                    rec.get("asset_id"),
                    rec["timestamp"],
                    rec.get("open"), rec.get("high"),
                    rec.get("low"), rec.get("close"),
                    rec.get("volume"), rec.get("trades_count"),
                ),
            )


def _get_tracked_pools() -> list[dict]:
    """Get pools we're already tracking in liquidity_depth."""
    from app.database import fetch_all

    rows = fetch_all(
        """SELECT DISTINCT asset_id, venue, chain, pool_address
           FROM liquidity_depth
           WHERE venue_type = 'dex'
             AND pool_address IS NOT NULL
             AND pool_address != ''
             AND snapshot_at > NOW() - INTERVAL '24 hours'
           ORDER BY asset_id"""
    )
    return [dict(r) for r in rows] if rows else []


async def run_ohlcv_collection() -> dict:
    """
    Fetch OHLCV data for all tracked DEX pools.
    """
    pools = _get_tracked_pools()
    if not pools:
        return {"pools_found": 0, "records_stored": 0}

    total_records = 0
    pools_processed = 0

    async with httpx.AsyncClient(timeout=30) as client:
        for pool in pools:
            chain = pool.get("chain", "ethereum")
            network = CHAIN_MAP.get(chain)
            pool_address = pool.get("pool_address")

            if not network or not pool_address:
                continue

            try:
                ohlcv_list = await _fetch_pool_ohlcv(
                    client, network, pool_address, timeframe="hour", limit=24
                )

                if not ohlcv_list:
                    continue

                records = []
                for candle in ohlcv_list:
                    # GeckoTerminal format: [timestamp, open, high, low, close, volume]
                    if not isinstance(candle, list) or len(candle) < 6:
                        continue

                    ts = datetime.fromtimestamp(candle[0], tz=timezone.utc)
                    records.append({
                        "pool_address": pool_address.lower(),
                        "chain": chain,
                        "dex": pool.get("venue"),
                        "asset_id": pool.get("asset_id"),
                        "timestamp": ts,
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": candle[5],
                        "trades_count": candle[6] if len(candle) > 6 else None,
                    })

                if records:
                    _store_ohlcv_records(records)
                    total_records += len(records)
                    pools_processed += 1

            except Exception as e:
                logger.debug(f"OHLCV collection failed for {pool_address[:10]}…: {e}")

    # Provenance
    try:
        from app.data_layer.provenance_scaling import attest_data_batch, link_batch_to_proof
        if total_records > 0:
            attest_data_batch("dex_pool_ohlcv", [{"records": total_records, "pools": pools_processed}])
            link_batch_to_proof("dex_pool_ohlcv", "liquidity_depth")
    except Exception:
        pass

    logger.info(
        f"OHLCV collection complete: {total_records} candles from "
        f"{pools_processed}/{len(pools)} pools"
    )

    return {
        "pools_found": len(pools),
        "pools_processed": pools_processed,
        "records_stored": total_records,
    }
