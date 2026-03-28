"""
PSI Data Collector
===================
Fetches protocol data from DeFiLlama's free API and scores protocols
using the generic scoring engine with the PSI v0.1 definition.
"""

import json
import logging
import time

import requests

from app.database import execute
from app.index_definitions.psi_v01 import PSI_V01_DEFINITION, TARGET_PROTOCOLS
from app.scoring_engine import score_entity

logger = logging.getLogger(__name__)

DEFILLAMA_BASE = "https://api.llama.fi"


def fetch_protocol_data(slug):
    """Fetch protocol data from DeFiLlama."""
    time.sleep(1)  # rate limit
    try:
        resp = requests.get(f"{DEFILLAMA_BASE}/protocol/{slug}", timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch {slug}: {e}")
        return None


def fetch_fees_data(slug):
    """Fetch fee/revenue data from DeFiLlama."""
    time.sleep(1)
    try:
        resp = requests.get(f"{DEFILLAMA_BASE}/summary/fees/{slug}", timeout=15)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
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
