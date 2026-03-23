"""
Wallet Indexer — Scanner
========================
Etherscan API integration: fetch ERC-20 token balances for a wallet address,
filtered to known stablecoin contracts.
"""

import os
import asyncio
import logging
from typing import Optional

import httpx

from app.indexer.config import (
    SCORED_CONTRACTS,
    UNSCORED_CONTRACTS,
    ALL_KNOWN_CONTRACTS,
    ETHERSCAN_RATE_LIMIT_DELAY,
)

logger = logging.getLogger(__name__)

ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"


async def fetch_token_balance(
    client: httpx.AsyncClient,
    contract_address: str,
    wallet_address: str,
    api_key: str,
) -> Optional[int]:
    """Fetch ERC-20 token balance for one wallet via Etherscan V2 API."""
    try:
        resp = await client.get(
            ETHERSCAN_V2_BASE,
            params={
                "chainid": 1,
                "module": "account",
                "action": "tokenbalance",
                "contractaddress": contract_address,
                "address": wallet_address,
                "tag": "latest",
                "apikey": api_key,
            },
            timeout=10.0,
        )
        data = resp.json()
        if data.get("status") == "1":
            return int(data["result"])
        msg = data.get("result", "")
        if "Max rate limit" in str(msg):
            logger.warning("Etherscan rate limit hit, backing off")
            await asyncio.sleep(1.0)
        return None
    except Exception as e:
        logger.debug(f"Balance fetch error {wallet_address[:10]}…: {e}")
        return None


async def fetch_token_list(
    client: httpx.AsyncClient,
    wallet_address: str,
    api_key: str,
) -> Optional[list[dict]]:
    """Fetch all ERC-20 token transfer events for a wallet to discover holdings.
    Uses tokentx action with a limited page size, then deduplicates contract addresses."""
    try:
        resp = await client.get(
            ETHERSCAN_V2_BASE,
            params={
                "chainid": 1,
                "module": "account",
                "action": "tokentx",
                "address": wallet_address,
                "page": 1,
                "offset": 100,
                "sort": "desc",
                "apikey": api_key,
            },
            timeout=15.0,
        )
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return data["result"]
        return None
    except Exception as e:
        logger.debug(f"Token list fetch error {wallet_address[:10]}…: {e}")
        return None


async def scan_wallet_holdings(
    client: httpx.AsyncClient,
    wallet_address: str,
    api_key: str,
    sii_scores: dict,
) -> list[dict]:
    """
    Scan a wallet for stablecoin holdings.

    For each known stablecoin contract (scored + unscored), queries the balance.
    Returns a list of holding dicts ready for storage.

    Args:
        client: httpx async client
        wallet_address: 0x-prefixed Ethereum address
        api_key: Etherscan API key
        sii_scores: dict of stablecoin_id → {overall_score, grade} from scores table
    """
    holdings = []

    for contract_lower, info in ALL_KNOWN_CONTRACTS.items():
        balance_raw = await fetch_token_balance(
            client, contract_lower, wallet_address, api_key
        )
        await asyncio.sleep(ETHERSCAN_RATE_LIMIT_DELAY)

        if balance_raw is None or balance_raw == 0:
            continue

        decimals = info.get("decimals", 18)
        balance = balance_raw / (10 ** decimals)

        # For stablecoins, price ≈ $1.00
        value_usd = balance

        # Check if this is a scored asset
        is_scored = contract_lower in SCORED_CONTRACTS
        sii_score = None
        sii_grade = None
        if is_scored:
            sid = SCORED_CONTRACTS[contract_lower]["stablecoin_id"]
            score_data = sii_scores.get(sid)
            if score_data:
                sii_score = score_data.get("overall_score")
                sii_grade = score_data.get("grade")

        holdings.append({
            "token_address": contract_lower,
            "symbol": info.get("symbol", "???"),
            "name": info.get("name", ""),
            "decimals": decimals,
            "balance": balance,
            "value_usd": value_usd,
            "is_scored": is_scored,
            "sii_score": sii_score,
            "sii_grade": sii_grade,
        })

    return holdings


async def fetch_top_holders(
    client: httpx.AsyncClient,
    contract_address: str,
    api_key: str,
    page: int = 1,
    offset: int = 100,
) -> list[str]:
    """
    Fetch top token holders for a contract via Etherscan tokeholderlist.
    Returns list of holder addresses. Falls back to empty list on failure.
    """
    try:
        resp = await client.get(
            ETHERSCAN_V2_BASE,
            params={
                "chainid": 1,
                "module": "token",
                "action": "tokenholderlist",
                "contractaddress": contract_address,
                "page": page,
                "offset": offset,
                "apikey": api_key,
            },
            timeout=15.0,
        )
        data = resp.json()
        if data.get("status") == "1" and isinstance(data.get("result"), list):
            return [h.get("TokenHolderAddress", "") for h in data["result"] if h.get("TokenHolderAddress")]
        return []
    except Exception as e:
        logger.debug(f"Top holders fetch error for {contract_address[:10]}…: {e}")
        return []
