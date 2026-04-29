"""
Actor Metrics Collector
=======================
Collects agent_holder_share and correlated_response_risk for SII scoring.
Queries wallet_graph.actor_classifications joined with wallet_graph.wallet_holdings
to compute actor composition metrics per stablecoin.

Part of Primitive #21: Actor Classification.
"""

import logging

from app.database import fetch_one, fetch_one_async

logger = logging.getLogger(__name__)


async def collect_actor_metrics(client, stablecoin_id: str) -> list[dict]:
    """Collect actor-composition scoring components for one stablecoin.

    Returns list of component dicts compatible with the scoring pipeline.
    """
    components = []

    try:
        # Get contract address for this stablecoin
        contract_row = await fetch_one_async(
            "SELECT contract FROM stablecoins WHERE id = %s",
            (stablecoin_id,),
        )
        if not contract_row or not contract_row.get("contract"):
            return components

        contract = contract_row["contract"].lower()

        # Agent holder share: % of USD value held by autonomous_agent wallets
        row = await fetch_one_async(
            """
            SELECT
                COALESCE(SUM(CASE WHEN ac.actor_type = 'autonomous_agent' THEN wh.value_usd ELSE 0 END), 0) AS agent_usd,
                COALESCE(SUM(wh.value_usd), 0) AS total_usd,
                COUNT(DISTINCT CASE WHEN ac.actor_type = 'autonomous_agent' THEN wh.wallet_address END) AS agent_wallets,
                COUNT(DISTINCT wh.wallet_address) AS total_wallets
            FROM wallet_graph.wallet_holdings wh
            LEFT JOIN wallet_graph.actor_classifications ac
                ON ac.wallet_address = wh.wallet_address
            WHERE LOWER(wh.token_address) = %s
              AND wh.indexed_at > NOW() - INTERVAL '7 days'
              AND wh.value_usd >= 0.01
            """,
            (contract,),
        )

        total_usd = float(row["total_usd"]) if row and row["total_usd"] else 0
        agent_usd = float(row["agent_usd"]) if row and row["agent_usd"] else 0
        agent_wallets = row["agent_wallets"] if row else 0
        total_wallets = row["total_wallets"] if row else 0

        agent_share_pct = (agent_usd / total_usd * 100) if total_usd > 0 else 0

        components.append({
            "component_id": "agent_holder_share",
            "category": "holder_distribution",
            "raw_value": round(agent_share_pct, 2),
            "data_source": "actor_classification",
            "metadata": {
                "description": f"{agent_share_pct:.1f}% of holdings by value are held by autonomous agents",
                "agent_value_usd": round(agent_usd, 2),
                "total_value_usd": round(total_usd, 2),
                "agent_wallets": agent_wallets,
                "total_wallets": total_wallets,
            },
        })

        # Correlated response risk: agent_share × agent HHI concentration
        # If agent holders are concentrated (few big agents), correlated exit risk is high
        if agent_wallets > 0 and agent_usd > 0:
            hhi_row = await fetch_one_async(
                """
                SELECT COALESCE(SUM(pct * pct), 0) AS hhi
                FROM (
                    SELECT wh.wallet_address,
                           wh.value_usd / NULLIF(SUM(wh.value_usd) OVER (), 0) * 100 AS pct
                    FROM wallet_graph.wallet_holdings wh
                    JOIN wallet_graph.actor_classifications ac
                        ON ac.wallet_address = wh.wallet_address
                    WHERE LOWER(wh.token_address) = %s
                      AND ac.actor_type = 'autonomous_agent'
                      AND wh.indexed_at > NOW() - INTERVAL '7 days'
                      AND wh.value_usd >= 0.01
                ) sub
                """,
                (contract,),
            )
            agent_hhi = float(hhi_row["hhi"]) if hhi_row and hhi_row["hhi"] else 0
            # Normalize HHI to 0-100 range (10000 = max, single holder)
            agent_hhi_norm = min(agent_hhi / 100, 100)
            # Correlated risk = agent_share% × agent_concentration_factor
            correlated_risk = agent_share_pct * agent_hhi_norm / 100
        else:
            correlated_risk = 0
            agent_hhi = 0

        components.append({
            "component_id": "correlated_response_risk",
            "category": "holder_distribution",
            "raw_value": round(correlated_risk, 2),
            "data_source": "actor_classification",
            "metadata": {
                "description": f"Correlated response risk: {correlated_risk:.1f}% (agent_share × concentration)",
                "agent_holder_share_pct": round(agent_share_pct, 2),
                "agent_hhi": round(agent_hhi, 2),
            },
        })

    except Exception as e:
        logger.warning(f"Actor metrics collection failed for {stablecoin_id}: {e}")

    return components
