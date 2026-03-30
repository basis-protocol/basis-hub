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


def fetch_treasury_data(slug):
    """Fetch protocol treasury data from DeFiLlama."""
    time.sleep(1)
    try:
        resp = requests.get(f"{DEFILLAMA_BASE}/treasury/{slug}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"Treasury fetch failed for {slug}: {e}")
    return None


# Known bad debt events (static config — updated manually)
KNOWN_BAD_DEBT = {
    "aave": 0,
    "lido": 0,
    "eigenlayer": 0,
    "sky": 0,  # historically had some, long resolved
    "compound-finance": 0,
    "uniswap": 0,
    "curve-finance": 0,
    "morpho": 0,
    "spark": 0,
    "convex-finance": 0,
}

# Protocol main contract addresses for admin key analysis
PROTOCOL_CONTRACTS = {
    "aave": "0x7Fc66500c84A76Ad7e9c93437bFc5Ac33E2DDaE9",        # AAVE token
    "lido": "0xae7ab96520DE3A18E5e111B5EaAb095312D7fE84",        # stETH
    "eigenlayer": "0x858646372CC42E1A627fcE94aa7A7033e7CF075A",   # Strategy Manager
    "sky": "0x9f8F72aA9304c8B593d555F12eF6589cC3A579A2",         # MKR token
    "compound-finance": "0xc0Da02939E1441F497fd74F78cE7Decb17B66529", # Governance
    "uniswap": "0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984",     # UNI token
    "curve-finance": "0xD533a949740bb3306d119CC777fa900bA034cd52",  # CRV token
    "morpho": "0x9994E35Db50125E0DF82e4c2dde62496CE330999",       # Morpho token
    "spark": None,
    "convex-finance": "0x4e3FBD56CD56c3e72c1403e103b45Db9da5B9D2B", # CVX token
}


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


def extract_raw_values(protocol_data, fees_data, treasury_data=None):
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

        # Revenue efficiency — revenue / TVL annualized
        if raw.get("revenue_30d") and raw.get("tvl") and raw["tvl"] > 0:
            raw["fees_tvl_efficiency"] = (raw["revenue_30d"] * 12) / raw["tvl"]

    # Treasury data
    if treasury_data:
        chain_tvls = treasury_data.get("chainTvls", {})
        treasury_total = 0
        stablecoin_total = 0

        for chain_name, chain_data in chain_tvls.items():
            if isinstance(chain_data, dict):
                tvl_list = chain_data.get("tvl", [])
                if tvl_list:
                    last = tvl_list[-1]
                    if isinstance(last, dict):
                        treasury_total += last.get("totalLiquidityUSD", 0)

        if treasury_total > 0:
            raw["treasury_total_usd"] = treasury_total
            # Estimate stablecoin portion — conservative 20% if we can't parse token breakdown
            raw["treasury_stablecoin_pct"] = 20.0  # default

    return raw


def score_protocol(slug):
    """Fetch data and score a single protocol."""
    protocol_data = fetch_protocol_data(slug)
    fees_data = fetch_fees_data(slug)

    if not protocol_data:
        return None

    treasury_data = fetch_treasury_data(slug)
    raw_values = extract_raw_values(protocol_data, fees_data, treasury_data)

    # Bad debt (static config)
    bad_debt = KNOWN_BAD_DEBT.get(slug, 0)
    tvl = raw_values.get("tvl", 0)
    if tvl > 0:
        raw_values["bad_debt_ratio"] = (bad_debt / tvl) * 100  # as percentage of TVL
    else:
        raw_values["bad_debt_ratio"] = 0

    # Governance token data from CoinGecko
    gecko_id = PROTOCOL_GOVERNANCE_TOKENS.get(slug)
    token_data = None
    if gecko_id:
        token_data = fetch_coingecko_token(gecko_id)
        if token_data:
            market = token_data.get("market_data", {})
            # token_volume_24h
            vol = market.get("total_volume", {}).get("usd")
            if vol:
                raw_values["token_volume_24h"] = vol
            # token_liquidity_depth — volume/mcap ratio
            mcap = market.get("market_cap", {}).get("usd")
            if vol and mcap and mcap > 0:
                raw_values["token_liquidity_depth"] = vol / mcap
            # token_price_volatility_30d — use 30d price change as proxy
            pct_30d = market.get("price_change_percentage_30d")
            if pct_30d is not None:
                raw_values["token_price_volatility_30d"] = abs(pct_30d)
            # governance_token_holders
            holders = token_data.get("community_data", {}).get("token_holders")
            if holders and holders > 0:
                raw_values["governance_token_holders"] = holders

    # Governance proposals from Snapshot
    space_id = SNAPSHOT_SPACES.get(slug)
    if space_id:
        proposal_count = fetch_snapshot_proposals(space_id)
        if proposal_count is not None:
            raw_values["governance_proposals_90d"] = proposal_count

    # Protocol admin key risk — reuse SII smart contract analyzer config
    from app.collectors.smart_contract import ADMIN_KEY_RISK
    contract = PROTOCOL_CONTRACTS.get(slug)
    if contract:
        # Use SII admin key scores if protocol has a matching stablecoin entry
        # Otherwise use a reasonable default based on protocol type
        admin_score = ADMIN_KEY_RISK.get(slug)
        if admin_score is None:
            # Map protocols to admin risk based on known governance structure
            admin_score = _PROTOCOL_ADMIN_SCORES.get(slug, 50)
        raw_values["protocol_admin_key_risk"] = admin_score

    result = score_entity(PSI_V01_DEFINITION, raw_values)
    result["protocol_slug"] = slug
    result["protocol_name"] = protocol_data.get("name", slug)
    result["raw_values"] = raw_values

    return result


# Protocol admin risk scores (separate from stablecoin scores)
_PROTOCOL_ADMIN_SCORES = {
    "aave": 90,        # Aave Gov V3 — on-chain governance
    "lido": 85,        # LidoDAO — on-chain governance + multisig
    "eigenlayer": 60,   # Early stage, team-controlled
    "sky": 90,         # MakerDAO — on-chain governance (DSChief)
    "compound-finance": 85,  # Compound Governor Bravo
    "uniswap": 85,     # Uniswap Governance — on-chain
    "curve-finance": 85, # veCRV governance
    "morpho": 65,      # Newer protocol, multisig governance
    "spark": 70,       # Sub-DAO of MakerDAO
    "convex-finance": 75, # Multisig + veCVX governance
}


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
