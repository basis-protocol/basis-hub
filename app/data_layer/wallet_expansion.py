"""
Autonomous Wallet Graph Expansion
===================================
Target: every wallet that has ever held >$100K in any scored stablecoin
across Ethereum, Base, and Arbitrum.

Strategy: crawl outward from existing graph. Every day, take wallets at the
edge — fewest connections — pull their transaction histories via Etherscan.
Discover new counterparties. Insert them. Next day, do the next batch.

At 432K Etherscan calls/day, we can balance-check every wallet in the graph
daily AND grow it.

Uses the shared rate limiter and API budget manager.
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def run_wallet_graph_expansion(
    target_new_wallets: int = 500,
    max_etherscan_calls: int = 2000,
) -> dict:
    """
    Expand the wallet graph by discovering new counterparties.

    Strategy:
    1. Find edge wallets (fewest connections, highest value)
    2. Pull their recent transfer histories via Etherscan
    3. Extract counterparty addresses
    4. Filter to addresses not already in graph
    5. Seed new wallets

    Args:
        target_new_wallets: Target number of new wallets to discover
        max_etherscan_calls: Budget cap for Etherscan calls

    Returns:
        Summary of expansion results.
    """
    import httpx
    import os
    from app.database import fetch_all, fetch_one, execute, get_cursor
    from app.shared_rate_limiter import rate_limiter
    from app.api_usage_tracker import track_api_call

    ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
    if not ETHERSCAN_API_KEY:
        return {"error": "ETHERSCAN_API_KEY not set"}

    # 1. Find edge wallets: high value, few connections
    edge_wallets = fetch_all(
        """SELECT w.address, r.total_stablecoin_value,
                  COALESCE(e.edge_count, 0) as edge_count
           FROM wallet_graph.wallets w
           JOIN wallet_graph.wallet_risk_scores r ON w.address = r.wallet_address
           LEFT JOIN (
               SELECT source_address as address, COUNT(*) as edge_count
               FROM wallet_graph.wallet_edges
               GROUP BY source_address
           ) e ON w.address = e.address
           WHERE r.total_stablecoin_value >= 100000
           ORDER BY COALESCE(e.edge_count, 0) ASC, r.total_stablecoin_value DESC
           LIMIT %s""",
        (target_new_wallets,),
    )

    if not edge_wallets:
        return {"error": "no edge wallets found for expansion"}

    calls_used = 0
    new_wallets_discovered = 0
    wallets_processed = 0
    discovered_addresses = set()

    # Get existing wallet set for dedup
    existing = fetch_all("SELECT address FROM wallet_graph.wallets")
    existing_set = set(r["address"].lower() for r in existing) if existing else set()

    async with httpx.AsyncClient(timeout=15) as client:
        for wallet in edge_wallets:
            if calls_used >= max_etherscan_calls:
                break

            address = wallet["address"]

            # 2. Fetch recent token transfers for this wallet
            try:
                await rate_limiter.acquire("etherscan")
                start = time.time()

                resp = await client.get(
                    "https://api.etherscan.io/v2/api",
                    params={
                        "chainid": 1,
                        "module": "account",
                        "action": "tokentx",
                        "address": address,
                        "startblock": 0,
                        "endblock": 99999999,
                        "page": 1,
                        "offset": 50,
                        "sort": "desc",
                        "apikey": ETHERSCAN_API_KEY,
                    },
                    timeout=15,
                )

                latency = int((time.time() - start) * 1000)
                track_api_call("etherscan", "/tokentx",
                               caller="wallet_expansion", status=resp.status_code,
                               latency_ms=latency)
                calls_used += 1

                if resp.status_code == 429 or "Max rate limit" in resp.text:
                    rate_limiter.report_429("etherscan")
                    continue

                rate_limiter.report_success("etherscan")
                data = resp.json()

                if data.get("status") != "1":
                    continue

                # 3. Extract counterparty addresses
                transfers = data.get("result", [])
                for tx in transfers:
                    for addr_field in ["from", "to"]:
                        counterparty = (tx.get(addr_field) or "").lower()
                        if (
                            counterparty
                            and counterparty != address.lower()
                            and counterparty != "0x0000000000000000000000000000000000000000"
                            and counterparty not in existing_set
                            and counterparty not in discovered_addresses
                            and counterparty.startswith("0x")
                            and len(counterparty) == 42
                        ):
                            discovered_addresses.add(counterparty)

                wallets_processed += 1

            except Exception as e:
                logger.debug(f"Expansion transfer fetch failed for {address}: {e}")

    # 4. Seed new wallets (batch insert)
    if discovered_addresses:
        batch = list(discovered_addresses)[:target_new_wallets]
        try:
            with get_cursor() as cur:
                for addr in batch:
                    cur.execute(
                        """INSERT INTO wallet_graph.wallets (address, source, created_at)
                           VALUES (%s, 'graph_expansion', NOW())
                           ON CONFLICT (address) DO NOTHING""",
                        (addr,),
                    )
            new_wallets_discovered = len(batch)
        except Exception as e:
            logger.warning(f"Wallet expansion insert failed: {e}")

    # Update graph stats
    try:
        total_wallets = fetch_one("SELECT COUNT(*) as cnt FROM wallet_graph.wallets")
        total_count = total_wallets["cnt"] if total_wallets else 0
    except Exception:
        total_count = "unknown"

    logger.info(
        f"Wallet expansion complete: processed {wallets_processed} edge wallets, "
        f"discovered {new_wallets_discovered} new addresses, "
        f"used {calls_used} Etherscan calls, total graph: {total_count}"
    )

    return {
        "edge_wallets_processed": wallets_processed,
        "new_wallets_discovered": new_wallets_discovered,
        "etherscan_calls_used": calls_used,
        "total_graph_size": total_count,
    }
