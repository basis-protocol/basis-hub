"""
Provenance Scaling
===================
Expand TLSNotary sample provenance to cover all data layer tiers.

Strategy — SAMPLE PROVENANCE:
- For each data type, prove ONE representative call per cycle
- The proven call anchors the batch — same code path
- Store proof alongside data batch

Expands from 4 sources to ~12-15 sources, still hourly, still manageable.
Every data table gets a provenance_proof_id linking back to nearest proof.
"""

import json
import logging
from datetime import datetime, timezone

from app.database import fetch_one, execute, fetch_all

logger = logging.getLogger(__name__)

# Provenance source registry — maps data types to representative endpoints
PROVENANCE_SOURCES = {
    # Existing (from V7.8)
    "coingecko_price": {
        "provider": "coingecko",
        "endpoint": "/coins/usd-coin",
        "data_types": ["scores", "component_readings"],
        "description": "CoinGecko coin data — anchors SII price/volume components",
    },
    "defillama_tvl": {
        "provider": "defillama",
        "endpoint": "/tvl/aave",
        "data_types": ["psi_scores"],
        "description": "DeFiLlama TVL — anchors PSI collateral components",
    },
    "etherscan_holders": {
        "provider": "etherscan",
        "endpoint": "/tokenholdercount",
        "data_types": ["wallet_holdings"],
        "description": "Etherscan holder data — anchors distribution components",
    },
    "snapshot_governance": {
        "provider": "snapshot",
        "endpoint": "/graphql",
        "data_types": ["governance_proposals"],
        "description": "Snapshot proposals — anchors governance components",
    },

    # NEW — Universal Data Layer sources
    "geckoterminal_dex": {
        "provider": "coingecko",
        "endpoint": "/onchain/networks/eth/tokens/{address}/pools",
        "data_types": ["liquidity_depth"],
        "description": "GeckoTerminal DEX pools — anchors Tier 1 liquidity depth",
    },
    "coingecko_tickers": {
        "provider": "coingecko",
        "endpoint": "/coins/usd-coin/tickers",
        "data_types": ["liquidity_depth"],
        "description": "CoinGecko CEX tickers — anchors Tier 1 CEX liquidity",
    },
    "defillama_yields": {
        "provider": "defillama",
        "endpoint": "/pools",
        "data_types": ["yield_snapshots"],
        "description": "DeFiLlama yield pools — anchors Tier 2 yield data",
    },
    "defillama_bridges": {
        "provider": "defillama",
        "endpoint": "/bridges",
        "data_types": ["bridge_flows"],
        "description": "DeFiLlama bridges — anchors Tier 4 bridge flows",
    },
    "coingecko_exchanges": {
        "provider": "coingecko",
        "endpoint": "/exchanges/binance",
        "data_types": ["exchange_snapshots"],
        "description": "CoinGecko exchange data — anchors Tier 5 exchange snapshots",
    },
    "coingecko_market_chart": {
        "provider": "coingecko",
        "endpoint": "/coins/usd-coin/market_chart",
        "data_types": ["peg_snapshots_5m", "volatility_surfaces"],
        "description": "CoinGecko market chart — anchors 5-min peg + volatility",
    },
    "etherscan_tokentx": {
        "provider": "etherscan",
        "endpoint": "/tokentx",
        "data_types": ["mint_burn_events"],
        "description": "Etherscan token transfers — anchors mint/burn events",
    },
    "etherscan_sourcecode": {
        "provider": "etherscan",
        "endpoint": "/getsourcecode",
        "data_types": ["contract_surveillance"],
        "description": "Etherscan source code — anchors contract surveillance",
    },
    "blockscout_balances": {
        "provider": "blockscout",
        "endpoint": "/v2/addresses/{address}/token-balances",
        "data_types": ["wallet_holdings"],
        "description": "Blockscout token balances — anchors wallet graph data",
    },
    "tally_governance": {
        "provider": "tally",
        "endpoint": "/query",
        "data_types": ["governance_proposals"],
        "description": "Tally on-chain governance — anchors Tier 3 governance data",
    },
}


def get_provenance_registry() -> dict:
    """Return the full provenance source registry with current proof status."""
    registry = {}

    for source_id, source in PROVENANCE_SOURCES.items():
        # Check latest proof for this source
        latest_proof = None
        try:
            row = fetch_one(
                """SELECT proved_at, attestation_hash
                   FROM provenance_proofs
                   WHERE source_domain = %s
                   ORDER BY proved_at DESC LIMIT 1""",
                (source_id,),
            )
            if row:
                latest_proof = {
                    "proved_at": row["proved_at"].isoformat() if row.get("proved_at") else None,
                    "hash": row.get("attestation_hash"),
                }
        except Exception:
            pass

        registry[source_id] = {
            **source,
            "latest_proof": latest_proof,
            "status": "proven" if latest_proof else "unproven",
        }

    return registry


def get_data_type_provenance(data_type: str) -> dict:
    """Get provenance chain for a specific data type."""
    matching_sources = []
    for source_id, source in PROVENANCE_SOURCES.items():
        if data_type in source["data_types"]:
            matching_sources.append(source_id)

    if not matching_sources:
        return {
            "data_type": data_type,
            "provenance_status": "no_source_registered",
            "sources": [],
        }

    proofs = []
    for source_id in matching_sources:
        try:
            rows = fetch_all(
                """SELECT proved_at, attestation_hash, source_domain
                   FROM provenance_proofs
                   WHERE source_domain = %s
                   ORDER BY proved_at DESC LIMIT 5""",
                (source_id,),
            )
            if rows:
                proofs.extend([dict(r) for r in rows])
        except Exception:
            pass

    return {
        "data_type": data_type,
        "provenance_status": "proven" if proofs else "unproven",
        "registered_sources": matching_sources,
        "recent_proofs": proofs[:10],
    }


def update_catalog_provenance():
    """Update data_catalog with provenance status for each data type."""
    for source_id, source in PROVENANCE_SOURCES.items():
        for data_type in source["data_types"]:
            try:
                # Check if proof exists within staleness threshold
                row = fetch_one(
                    """SELECT proved_at FROM provenance_proofs
                       WHERE source_domain = %s
                         AND proved_at > NOW() - INTERVAL '24 hours'
                       ORDER BY proved_at DESC LIMIT 1""",
                    (source_id,),
                )
                status = "proven" if row else "unproven"

                execute(
                    """UPDATE data_catalog
                       SET provenance_status = %s, updated_at = NOW()
                       WHERE data_type = %s""",
                    (status, data_type),
                )
            except Exception:
                pass

    logger.info("Data catalog provenance status updated")
