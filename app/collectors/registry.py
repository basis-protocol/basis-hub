"""
Collector Registry
===================
Declarative registry for SII data collectors.
Auto-instrumentation: timing, error tracking, CycleStats persistence.

To add a new async collector:
    Add one entry to _make_async_collectors().

To add a new sync collector:
    Add one entry to _make_sync_collectors().
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from app.database import execute, get_cursor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CycleStats — per-cycle performance tracking
# ---------------------------------------------------------------------------

class CycleStats:
    """Accumulates per-collector stats across all coins in a scoring cycle."""

    def __init__(self):
        self._data = defaultdict(lambda: {
            "ok": 0,
            "timeout": 0,
            "error": 0,
            "latencies": [],
            "components": 0,
        })

    def record_ok(self, name: str, latency_ms: int, component_count: int):
        entry = self._data[name]
        entry["ok"] += 1
        entry["latencies"].append(latency_ms)
        entry["components"] += component_count

    def record_timeout(self, name: str):
        self._data[name]["timeout"] += 1

    def record_error(self, name: str):
        self._data[name]["error"] += 1

    def log_summary(self):
        if not self._data:
            logger.info("CycleStats: no collector data recorded")
            return
        logger.info("=== Collector cycle stats ===")
        for name, d in sorted(self._data.items()):
            avg_ms = (
                int(sum(d["latencies"]) / len(d["latencies"]))
                if d["latencies"]
                else 0
            )
            logger.info(
                f"  {name:30s}  ok={d['ok']:3d}  timeout={d['timeout']:2d}  "
                f"error={d['error']:2d}  avg={avg_ms:5d}ms  components={d['components']}"
            )

    def store(self):
        """Persist stats to collector_cycle_stats table."""
        if not self._data:
            return
        try:
            with get_cursor() as cur:
                for name, d in self._data.items():
                    avg_ms = (
                        int(sum(d["latencies"]) / len(d["latencies"]))
                        if d["latencies"]
                        else 0
                    )
                    cur.execute(
                        """
                        INSERT INTO collector_cycle_stats
                            (collector_name, coins_ok, coins_timeout, coins_error,
                             avg_latency_ms, total_components)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (name, d["ok"], d["timeout"], d["error"],
                         avg_ms, d["components"]),
                    )
        except Exception as e:
            logger.warning(f"Failed to store cycle stats: {e}")


# ---------------------------------------------------------------------------
# Collector descriptors
# ---------------------------------------------------------------------------

def _make_async_collectors():
    """
    Return list of (name, callable) for async collectors.
    Each callable has signature: (client, coingecko_id, stablecoin_id) -> list[dict].
    Collectors that only need (client, stablecoin_id) are wrapped to ignore cg_id.
    """
    from app.collectors.coingecko import (
        collect_peg_components,
        collect_liquidity_components,
        collect_market_activity_components,
    )
    from app.collectors.defillama import collect_defillama_components
    from app.collectors.curve import collect_curve_components
    from app.collectors.etherscan import collect_holder_distribution
    from app.collectors.flows import collect_flows_components
    from app.collectors.smart_contract import collect_smart_contract_components
    from app.collectors.solana import collect_solana_components
    from app.collectors.actor_metrics import collect_actor_metrics

    # Wrappers to normalise signature to (client, cg_id, stablecoin_id)
    async def _curve(client, _cg_id, sid):
        return await collect_curve_components(client, sid)

    async def _etherscan(client, _cg_id, sid):
        return await collect_holder_distribution(client, sid)

    async def _flows(client, _cg_id, sid):
        return await collect_flows_components(client, sid)

    async def _smart_contract(client, _cg_id, sid):
        return await collect_smart_contract_components(client, sid)

    async def _solana(client, _cg_id, sid):
        return await collect_solana_components(client, sid)

    async def _actor(client, _cg_id, sid):
        return await collect_actor_metrics(client, sid)

    return [
        ("peg", collect_peg_components),
        ("liquidity", collect_liquidity_components),
        ("market", collect_market_activity_components),
        ("defillama", collect_defillama_components),
        ("curve", _curve),
        ("etherscan", _etherscan),
        ("flows", _flows),
        ("smart_contract", _smart_contract),
        ("solana", _solana),
        ("actor_metrics", _actor),
    ]


def _make_sync_collectors():
    """
    Return list of (name, callable) for sync collectors.
    Each callable has signature: (stablecoin_id) -> list[dict].
    """
    from app.collectors.offline import (
        collect_transparency_components,
        collect_regulatory_components,
        collect_governance_components,
        collect_reserve_components,
        collect_network_components,
    )
    from app.collectors.derived import collect_derived_components

    return [
        ("transparency", collect_transparency_components),
        ("regulatory", collect_regulatory_components),
        ("governance", collect_governance_components),
        ("reserves", collect_reserve_components),
        ("network", collect_network_components),
        ("derived", collect_derived_components),
    ]


# ---------------------------------------------------------------------------
# run_all_collectors — drop-in replacement for the old inline gather+loop
# ---------------------------------------------------------------------------

async def run_all_collectors(
    client,
    stablecoin_id: str,
    cfg: dict,
    cycle_stats: CycleStats | None = None,
    timeout: float = 20.0,
) -> list[dict]:
    """
    Run every registered SII collector for one stablecoin.
    Returns flat list of component dicts (not yet tagged with stablecoin_id).
    """
    cg_id = cfg["coingecko_id"]
    all_components: list[dict] = []

    # --- async collectors (parallel with per-collector timeout) ---
    async_collectors = _make_async_collectors()

    async def _instrumented(name, coro):
        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(coro, timeout=timeout)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            count = len(result) if result else 0
            if cycle_stats:
                cycle_stats.record_ok(name, elapsed_ms, count)
            return result or []
        except asyncio.TimeoutError:
            logger.warning(f"{name} timed out for {stablecoin_id}")
            if cycle_stats:
                cycle_stats.record_timeout(name)
            return []
        except Exception as e:
            logger.error(f"{name} error for {stablecoin_id}: {e}")
            if cycle_stats:
                cycle_stats.record_error(name)
            return []

    tasks = [
        _instrumented(name, fn(client, cg_id, stablecoin_id))
        for name, fn in async_collectors
    ]
    results = await asyncio.gather(*tasks)
    for result in results:
        if result:
            all_components.extend(result)

    # --- sync collectors (sequential, from config/scraped data) ---
    sync_collectors = _make_sync_collectors()
    for name, fn in sync_collectors:
        t0 = time.monotonic()
        try:
            result = fn(stablecoin_id)
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            count = len(result) if result else 0
            if cycle_stats:
                cycle_stats.record_ok(name, elapsed_ms, count)
            if result:
                all_components.extend(result)
        except Exception as e:
            logger.error(f"{name} error for {stablecoin_id}: {e}")
            if cycle_stats:
                cycle_stats.record_error(name)

    return all_components
