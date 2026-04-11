"""
Oracle Activity Monitor
=======================
Tracks external interactions with Basis oracle and SBT contracts on Base and
Arbitrum by polling block explorer APIs (Basescan / Arbiscan).

Keeper writes are filtered out. Everything remaining is evidence of external
adoption — other contracts or wallets calling functions on our contracts.

Note: EVM view/pure function calls (e.g. getScore) do NOT create transactions
and cannot be tracked via block explorer APIs. Only write-type interactions
that consume gas appear here. To track view calls at scale we would need call
tracing infrastructure (own RPC node with tracing, Tenderly, or Alchemy trace
API). This limitation is documented in DUNE_QUERIES.md.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

from app.database import execute, fetch_one, fetch_all

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORACLE_ADDRESS = "0x1651d7b2E238a952167E51A1263FFe607584DB83"
SBT_ADDRESS = "0xf315411e49fC3EAbEF0D111A40e976802985E56c"
KEEPER_ADDRESS = "0x2dF0f62D1861Aa59A4430e3B2b2E7a0D29Cb723b".lower()

# Known function selectors (first 4 bytes of keccak256 of signature)
KNOWN_SELECTORS = {
    "0x6e8fa984": "batchUpdateScores",
    "0x38a0c825": "publishReportHash",
    "0x6c0360eb": "publishStateRoot",
    "0x6a627842": "mint",
    "0x42966c68": "burn",
}

# Contracts to monitor: (label, chain, contract_type, address, explorer_base)
CONTRACTS = [
    {
        "label": "Oracle (Base)",
        "chain": "base",
        "contract_type": "oracle_base",
        "address": ORACLE_ADDRESS,
        "explorer_api": "https://api.basescan.org/api",
        "api_key_env": "BASESCAN_API_KEY",
    },
    {
        "label": "Oracle (Arbitrum)",
        "chain": "arbitrum",
        "contract_type": "oracle_arbitrum",
        "address": ORACLE_ADDRESS,
        "explorer_api": "https://api.arbiscan.io/api",
        "api_key_env": "ARBISCAN_API_KEY",
    },
    {
        "label": "SBT (Base)",
        "chain": "base",
        "contract_type": "sbt_base",
        "address": SBT_ADDRESS,
        "explorer_api": "https://api.basescan.org/api",
        "api_key_env": "BASESCAN_API_KEY",
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def poll_external_interactions() -> dict:
    """
    Poll all monitored contracts for recent transactions and store any
    non-keeper interactions. Returns summary counts per contract_type.
    """
    # Ensure table exists (idempotent)
    _ensure_table()

    summary = {}
    async with httpx.AsyncClient(timeout=20.0) as client:
        for contract in CONTRACTS:
            try:
                new_count = await _poll_contract(client, contract)
                summary[contract["contract_type"]] = new_count
            except Exception as e:
                logger.error(
                    f"Oracle monitor [{contract['label']}]: poll failed: {e}"
                )
                summary[contract["contract_type"]] = {"error": str(e)}

    # Log summary
    totals = sum(v for v in summary.values() if isinstance(v, int))
    parts = ", ".join(
        f"{k}: {v}" for k, v in summary.items() if isinstance(v, int)
    )
    logger.info(
        f"Oracle monitor: {totals} new external interactions found ({parts})"
    )
    return summary


async def _poll_contract(client: httpx.AsyncClient, contract: dict) -> int:
    """Fetch recent txs to a contract, filter out keeper, store new ones."""
    api_key = os.environ.get(contract["api_key_env"], "")
    params = {
        "module": "account",
        "action": "txlist",
        "address": contract["address"],
        "startblock": "0",
        "endblock": "99999999",
        "sort": "desc",
        "page": "1",
        "offset": "100",
    }
    if api_key:
        params["apikey"] = api_key

    resp = await client.get(contract["explorer_api"], params=params)
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "1" or not data.get("result"):
        # status "0" with message "No transactions found" is normal for new contracts
        if data.get("message") == "No transactions found":
            logger.debug(
                f"Oracle monitor [{contract['label']}]: no transactions found"
            )
            return 0
        logger.warning(
            f"Oracle monitor [{contract['label']}]: API returned "
            f"status={data.get('status')}, message={data.get('message')}"
        )
        return 0

    txs = data["result"]
    new_count = 0

    for tx in txs:
        from_addr = (tx.get("from") or "").lower()

        # Filter out keeper transactions
        if from_addr == KEEPER_ADDRESS:
            continue

        # Filter out failed transactions
        if tx.get("isError") == "1":
            continue

        tx_hash = tx.get("hash", "")
        if not tx_hash:
            continue

        # Check duplicate
        existing = fetch_one(
            "SELECT id FROM oracle_external_interactions WHERE tx_hash = %s",
            (tx_hash,),
        )
        if existing:
            continue

        # Parse function selector
        input_data = tx.get("input") or ""
        function_selector = input_data[:10] if len(input_data) >= 10 else None
        function_name = KNOWN_SELECTORS.get(function_selector)

        # Parse timestamp
        ts = None
        if tx.get("timeStamp"):
            try:
                ts = datetime.fromtimestamp(
                    int(tx["timeStamp"]), tz=timezone.utc
                )
            except (ValueError, OSError):
                pass

        block_number = int(tx["blockNumber"]) if tx.get("blockNumber") else None
        gas_used = int(tx["gasUsed"]) if tx.get("gasUsed") else None

        execute(
            """INSERT INTO oracle_external_interactions
               (chain, contract_type, tx_hash, from_address,
                function_selector, function_name,
                block_number, timestamp, gas_used)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (tx_hash) DO NOTHING""",
            (
                contract["chain"],
                contract["contract_type"],
                tx_hash,
                from_addr,
                function_selector,
                function_name,
                block_number,
                ts,
                gas_used,
            ),
        )
        new_count += 1

    logger.info(
        f"Oracle monitor [{contract['label']}]: "
        f"{new_count} new external interactions from {len(txs)} txs"
    )
    return new_count


# ---------------------------------------------------------------------------
# Metrics query (used by seed-metrics endpoint)
# ---------------------------------------------------------------------------

def get_oracle_activity_metrics() -> dict:
    """Return oracle activity summary for the seed-metrics endpoint."""
    _ensure_table()

    interactions_7d = fetch_one(
        "SELECT COUNT(*) as c FROM oracle_external_interactions "
        "WHERE timestamp > NOW() - INTERVAL '7 days'"
    )
    interactions_30d = fetch_one(
        "SELECT COUNT(*) as c FROM oracle_external_interactions "
        "WHERE timestamp > NOW() - INTERVAL '30 days'"
    )
    unique_addrs_7d = fetch_one(
        "SELECT COUNT(DISTINCT from_address) as c FROM oracle_external_interactions "
        "WHERE timestamp > NOW() - INTERVAL '7 days'"
    )
    latest = fetch_one(
        "SELECT MAX(timestamp) as ts FROM oracle_external_interactions"
    )
    by_chain = fetch_all(
        "SELECT contract_type, COUNT(*) as c FROM oracle_external_interactions "
        "WHERE timestamp > NOW() - INTERVAL '7 days' "
        "GROUP BY contract_type"
    ) or []

    chain_counts = {row["contract_type"]: row["c"] for row in by_chain}

    return {
        "external_interactions_7d": interactions_7d["c"] if interactions_7d else 0,
        "external_interactions_30d": interactions_30d["c"] if interactions_30d else 0,
        "unique_external_addresses_7d": unique_addrs_7d["c"] if unique_addrs_7d else 0,
        "latest_external_interaction": (
            latest["ts"].isoformat() if latest and latest["ts"] else None
        ),
        "by_chain": {
            "base_oracle": chain_counts.get("oracle_base", 0),
            "arbitrum_oracle": chain_counts.get("oracle_arbitrum", 0),
            "base_sbt": chain_counts.get("sbt_base", 0),
        },
    }


# ---------------------------------------------------------------------------
# Table bootstrap (idempotent)
# ---------------------------------------------------------------------------

def _ensure_table():
    """Create the oracle_external_interactions table if it doesn't exist."""
    execute("""
        CREATE TABLE IF NOT EXISTS oracle_external_interactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            chain VARCHAR(20) NOT NULL,
            contract_type VARCHAR(20) NOT NULL,
            tx_hash VARCHAR(66) NOT NULL UNIQUE,
            from_address VARCHAR(42) NOT NULL,
            function_selector VARCHAR(10),
            function_name VARCHAR(50),
            block_number BIGINT,
            timestamp TIMESTAMPTZ,
            gas_used BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
