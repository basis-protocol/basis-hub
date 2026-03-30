"""
PSI Data Collector
===================
Fetches protocol data from DeFiLlama's free API and scores protocols
using the generic scoring engine with the PSI v0.1 definition.
"""

import json
import logging
import time
from datetime import datetime, timezone

import requests

from app.database import execute
from app.index_definitions.psi_v01 import PSI_V01_DEFINITION, TARGET_PROTOCOLS
from app.scoring_engine import score_entity

logger = logging.getLogger(__name__)

DEFILLAMA_BASE = "https://api.llama.fi"

# Governance token CoinGecko IDs for protocols that have one
PROTOCOL_GOVERNANCE_TOKENS = {
    "aave": "aave",
    "lido": "lido-dao",
    "eigenlayer": "eigenlayer",
    "sky": "maker",  # MKR is still the governance token
    "compound-finance": "compound-governance-token",
    "uniswap": "uniswap",
    "curve-finance": "curve-dao-token",
    "morpho": "morpho",
    "spark": None,  # no separate governance token
    "convex-finance": "convex-finance",
}

# Snapshot space IDs for governance proposal queries
SNAPSHOT_SPACES = {
    "aave": "aave.eth",
    "lido": "lido-snapshot.eth",
    "sky": "makerdao.eth",
    "compound-finance": "comp-vote.eth",
    "uniswap": "uniswapgovernance.eth",
    "curve-finance": "curve.eth",
    "convex-finance": "cvx.eth",
}


def fetch_protocol_data(slug):
    """Fetch protocol data from DeFiLlama."""
    time.sleep(1)  # rate limit
    try:
        resp = requests.get(f"{DEFILLAMA_BASE}/protocol/{slug}", timeout=45)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch {slug}: {e}")
        return None


def fetch_fees_data(slug):
    """Fetch fee/revenue data from DeFiLlama."""
    time.sleep(1)
    try:
        resp = requests.get(f"{DEFILLAMA_BASE}/summary/fees/{slug}", timeout=45)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def fetch_coingecko_token(gecko_id):
    """Fetch governance token data from CoinGecko for holder count and volume."""
    if not gecko_id:
        return None
    time.sleep(1)
    try:
        from app.config import STABLECOIN_REGISTRY
        # Use the same API key pattern as the SII collectors
        import os
        api_key = os.environ.get("COINGECKO_API_KEY", "")
        headers = {"x-cg-pro-api-key": api_key} if api_key else {}
        base = "https://pro-api.coingecko.com/api/v3" if api_key else "https://api.coingecko.com/api/v3"

        resp = requests.get(
            f"{base}/coins/{gecko_id}",
            params={"localization": "false", "tickers": "false", "market_data": "true",
                    "community_data": "false", "developer_data": "false"},
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"CoinGecko token fetch failed for {gecko_id}: {e}")
    return None


def fetch_snapshot_proposals(space_id):
    """Fetch governance proposal count from Snapshot in the last 90 days."""
    if not space_id:
        return None
    time.sleep(0.5)
    try:
        query = """
        query {
          proposals(
            first: 100,
            skip: 0,
            where: {space: "%s", created_gte: %d},
            orderBy: "created",
            orderDirection: desc
          ) { id }
        }
        """ % (space_id, int((datetime.now(timezone.utc).timestamp()) - 90 * 86400))

        resp = requests.post(
            "https://hub.snapshot.org/graphql",
            json={"query": query},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            proposals = data.get("data", {}).get("proposals", [])
            return len(proposals)
    except Exception as e:
        logger.debug(f"Snapshot fetch failed for {space_id}: {e}")
    return None


def extract_raw_values(protocol_data, fees_data):
    """Extract raw component values from DeFiLlama data."""
    raw = {}

    if not protocol_data:
        return raw

    # TVL — /protocol/ returns tvl as a historical list; extract latest value
    tvl_raw = protocol_data.get("tvl")
    if isinstance(tvl_raw, list) and tvl_raw:
        last_entry = tvl_raw[-1]
        raw["tvl"] = last_entry.get("totalLiquidityUSD", 0) if isinstance(last_entry, dict) else 0
    elif isinstance(tvl_raw, (int, float)):
        raw["tvl"] = tvl_raw

    # TVL changes
    change_1w = protocol_data.get("change_7d")
    change_1m = protocol_data.get("change_1m")
    if change_1w is not None:
        raw["tvl_7d_change"] = change_1w
    if change_1m is not None:
        raw["tvl_30d_change"] = change_1m

    # Chain count and concentration — use currentChainTvls (snapshot) over chainTvls (historical)
    current_chain_tvls = protocol_data.get("currentChainTvls", {})
    if current_chain_tvls:
        # Filter out derivative entries like "Ethereum-borrowed", "Ethereum-staking", "Ethereum-pool2"
        chains_with_tvl = {
            k: v for k, v in current_chain_tvls.items()
            if "-" not in k and isinstance(v, (int, float)) and v > 0
        }

        raw["chain_count"] = len(chains_with_tvl)
        if chains_with_tvl:
            total_chain = sum(chains_with_tvl.values())
            if total_chain > 0:
                max_chain = max(chains_with_tvl.values())
                raw["tvl_concentration"] = (max_chain / total_chain) * 100

    # Audit info
    audits = protocol_data.get("audits")
    audit_links = protocol_data.get("audit_links", [])
    if audits is not None:
        raw["audit_count"] = int(audits) if audits else len(audit_links)
    elif audit_links:
        raw["audit_count"] = len(audit_links)

    # Audit recency — estimate from audit_links or audit_note
    # DeFiLlama doesn't always include timestamps, so use protocol launch date as fallback
    if audit_links:
        # Many audit links contain dates in the URL or name
        # Conservative estimate: if audits exist, assume most recent was within 365 days
        # unless the protocol is very old
        raw["audit_recency_days"] = 365  # conservative default if audits exist
    else:
        raw["audit_recency_days"] = 730  # no audits known

    # Liquidity & Utilization — use TVL as liquidity proxy
    # For lending protocols, compute utilization from borrowed/supplied
    tvl_val = raw.get("tvl", 0)
    if tvl_val and tvl_val > 0:
        raw["protocol_dex_tvl"] = tvl_val  # TVL IS the liquidity for protocols

        # Pool depth: number of active pools approximated from chain count × 2
        chain_ct = raw.get("chain_count", 1)
        raw["pool_depth"] = chain_ct * 3  # rough approximation: ~3 pools per chain

    # Utilization rate from borrowed TVL if available
    borrowed_tvl = 0
    staking_tvl = 0
    for k, v in current_chain_tvls.items() if current_chain_tvls else []:
        if "-borrowed" in k and isinstance(v, (int, float)):
            borrowed_tvl += v
        if "-staking" in k and isinstance(v, (int, float)):
            staking_tvl += v

    if borrowed_tvl > 0 and tvl_val > 0:
        raw["utilization_rate"] = (borrowed_tvl / (tvl_val + borrowed_tvl)) * 100
    elif staking_tvl > 0 and tvl_val > 0:
        # For staking protocols: staking ratio as utilization proxy
        raw["utilization_rate"] = (staking_tvl / (tvl_val + staking_tvl)) * 100

    # Token data (if available)
    mcap = protocol_data.get("mcap")
    if mcap:
        raw["token_mcap"] = mcap
        if raw.get("tvl") and raw["tvl"] > 0:
            raw["mcap_tvl_ratio"] = mcap / raw["tvl"]

    # Fees and revenue
    if fees_data:
        total_30d = fees_data.get("total30d")
        if total_30d:
            raw["fees_30d"] = total_30d
        revenue_30d = fees_data.get("totalRevenue30d")
        if revenue_30d:
            raw["revenue_30d"] = revenue_30d
        elif total_30d:
            raw["revenue_30d"] = total_30d * 0.3  # estimate if not available

        if raw.get("fees_30d") and raw.get("tvl") and raw["tvl"] > 0:
            raw["fees_tvl_ratio"] = (raw["fees_30d"] * 12) / raw["tvl"]  # annualized

    return raw


def score_protocol(slug):
    """Fetch data and score a single protocol."""
    protocol_data = fetch_protocol_data(slug)
    fees_data = fetch_fees_data(slug)

    if not protocol_data:
        return None

    raw_values = extract_raw_values(protocol_data, fees_data)

    # Governance token data from CoinGecko
    gecko_id = PROTOCOL_GOVERNANCE_TOKENS.get(slug)
    if gecko_id:
        token_data = fetch_coingecko_token(gecko_id)
        if token_data:
            market = token_data.get("market_data", {})
            # token_volume_24h
            vol = market.get("total_volume", {}).get("usd")
            if vol:
                raw_values["token_volume_24h"] = vol
            # governance_token_holders (community data if available)
            # CoinGecko doesn't always have holder count; use market cap rank as proxy
            holders = token_data.get("community_data", {}).get("token_holders")
            if holders and holders > 0:
                raw_values["governance_token_holders"] = holders

    # Governance proposals from Snapshot
    space_id = SNAPSHOT_SPACES.get(slug)
    if space_id:
        proposal_count = fetch_snapshot_proposals(space_id)
        if proposal_count is not None:
            raw_values["governance_proposals_90d"] = proposal_count

    result = score_entity(PSI_V01_DEFINITION, raw_values)
    result["protocol_slug"] = slug
    result["protocol_name"] = protocol_data.get("name", slug)
    result["raw_values"] = raw_values

    return result


def run_psi_scoring():
    """Score all target protocols and store results."""
    results = []
    for slug in TARGET_PROTOCOLS:
        logger.info(f"Scoring protocol: {slug}")
        result = score_protocol(slug)
        if result:
            execute("""
                INSERT INTO psi_scores (protocol_slug, protocol_name, overall_score, grade,
                    category_scores, component_scores, raw_values, formula_version)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT ON CONSTRAINT psi_scores_protocol_slug_scored_date_key
                DO UPDATE SET
                    protocol_name = EXCLUDED.protocol_name,
                    overall_score = EXCLUDED.overall_score,
                    grade = EXCLUDED.grade,
                    category_scores = EXCLUDED.category_scores,
                    component_scores = EXCLUDED.component_scores,
                    raw_values = EXCLUDED.raw_values
            """, (
                result["protocol_slug"],
                result["protocol_name"],
                result["overall_score"],
                result["grade"],
                json.dumps(result["category_scores"]),
                json.dumps(result["component_scores"]),
                json.dumps(result["raw_values"], default=str),
                result["version"],
            ))
            results.append(result)
            logger.info(
                f"  {result['protocol_name']}: {result['overall_score']} ({result['grade']}) "
                f"- {result['components_available']}/{result['components_total']} components"
            )

    return results
