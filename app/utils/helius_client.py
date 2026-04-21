"""
Helius Client — Solana Historical Data
========================================
Async client for Helius RPC (enhanced Solana RPC).
Used by backfill scripts for Solana-native entities.

Requires HELIUS_API_KEY in env. If not set, all methods return empty.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
HELIUS_RPC = (
    f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    if HELIUS_API_KEY
    else ""
)

_semaphore = asyncio.Semaphore(5)


def is_available() -> bool:
    return bool(HELIUS_API_KEY)


async def _rpc_call(
    client: httpx.AsyncClient, method: str, params: list,
    retries: int = 3,
) -> dict | list | None:
    """Make a rate-limited Helius RPC call."""
    if not HELIUS_RPC:
        return None

    for attempt in range(retries):
        async with _semaphore:
            try:
                resp = await client.post(
                    HELIUS_RPC,
                    json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                    timeout=30,
                )
                if resp.status_code == 429:
                    await asyncio.sleep(2 ** (attempt + 1))
                    continue
                data = resp.json()
                if data.get("error"):
                    logger.debug(f"Helius RPC error: {data['error']}")
                    return None
                return data.get("result")
            except Exception as e:
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.warning(f"Helius RPC failed: {method}: {e}")
                    return None
    return None


async def get_signatures_for_address(
    client: httpx.AsyncClient, address: str,
    before: str = None, until: str = None, limit: int = 1000,
) -> list:
    """Get transaction signatures for an address."""
    params = [address, {"limit": limit}]
    if before:
        params[1]["before"] = before
    if until:
        params[1]["until"] = until
    result = await _rpc_call(client, "getSignaturesForAddress", params)
    return result or []


async def get_transaction(client: httpx.AsyncClient, signature: str) -> dict | None:
    """Get a parsed transaction by signature."""
    return await _rpc_call(client, "getTransaction", [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])


async def get_token_largest_accounts(client: httpx.AsyncClient, mint: str) -> list:
    """Get largest token account holders for a mint."""
    result = await _rpc_call(client, "getTokenLargestAccounts", [mint])
    return result.get("value", []) if isinstance(result, dict) else result or []


async def get_account_info(client: httpx.AsyncClient, address: str) -> dict | None:
    """Get account info with parsed data."""
    result = await _rpc_call(client, "getAccountInfo", [address, {"encoding": "jsonParsed"}])
    return result.get("value") if isinstance(result, dict) else result
