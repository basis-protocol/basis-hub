"""
Populate the incident_snapshots row for slug = rseth-2026-04-18.

This is a one-off freeze of the Q4 forum-reply data package from
audits/lsti_rseth_audit_2026-04-20.md. Values are captured from the
live /api/lsti/scores/{slug} endpoint when available; for operators
running this in environments without live API access, a fallback value
set is used that matches the audit's documented static values.

Usage:
    python scripts/populate_incident_rseth_2026_04_18.py

Idempotent — re-running updates captured_at and components_json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone

import requests

# Project path setup so we can import app.database without installing the package
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from app.database import execute  # noqa: E402

SLUG = "rseth-2026-04-18"
EVENT_DATE = date(2026, 4, 18)
TITLE = "Unbacked rsETH Minting via Kelp DAO LayerZero Bridge"
SUMMARY = (
    "116,500 rsETH (~$292M) minted without ETH backing, deposited as "
    "Aave V3 collateral, ~$196M WETH borrowed."
)

# The 6 components from audit Q4, in the audit's ranked order.
Q4_COMPONENTS = [
    "exploit_history_lst",
    "market_cap",
    "dex_pool_depth",
    "eth_peg_deviation",
    "top_holder_concentration",
    "peg_volatility_7d",
]

COMPONENT_META = {
    "exploit_history_lst": {
        "label": "Exploit History",
        "category": "smart_contract",
        "unit": "score",
        "source": "static, updated 2026-04-20",
        "note": "Static floor lowered 100 → 10 per audit.",
    },
    "market_cap": {
        "label": "Market Cap",
        "category": "liquidity",
        "unit": "USD",
        "source": "CoinGecko",
        "note": "Live at capture time.",
    },
    "dex_pool_depth": {
        "label": "DEX Pool Depth",
        "category": "liquidity",
        "unit": "USD",
        "source": "DeFiLlama",
        "note": "Live at capture time.",
    },
    "eth_peg_deviation": {
        "label": "ETH Peg Deviation",
        "category": "peg_stability",
        "unit": "%",
        "source": "CoinGecko",
        "note": "Live at capture time.",
    },
    "top_holder_concentration": {
        "label": "Top 10 Holder Share",
        "category": "distribution",
        "unit": "%",
        "source": "Etherscan",
        "note": "Live at capture time (24h cache).",
    },
    "peg_volatility_7d": {
        "label": "7d Peg Volatility",
        "category": "peg_stability",
        "unit": "%",
        "source": "CoinGecko",
        "note": "Live at capture time.",
    },
}

PEERS = [
    {"slug": "kelp-rseth", "name": "Kelp rsETH", "symbol": "rsETH"},
    {"slug": "lido-steth", "name": "Lido stETH", "symbol": "stETH"},
    {"slug": "rocket-pool-reth", "name": "Rocket Pool rETH", "symbol": "rETH"},
    {"slug": "etherfi-eeth", "name": "EtherFi eETH", "symbol": "eETH"},
]

# Fallback values if the live API is unreachable. These mirror the
# static_config values documented in audits/lsti_rseth_audit_2026-04-20.md
# for exploit_history_lst (the only component whose value we know precisely
# without a live query) and use None otherwise so the page renders
# "—" instead of a fabricated number.
FALLBACK_VALUES = {
    "kelp-rseth": {
        "exploit_history_lst": 10,
        "market_cap": None,
        "dex_pool_depth": None,
        "eth_peg_deviation": None,
        "top_holder_concentration": None,
        "peg_volatility_7d": None,
    },
    "lido-steth": {
        "exploit_history_lst": 100,
        "market_cap": None,
        "dex_pool_depth": None,
        "eth_peg_deviation": None,
        "top_holder_concentration": None,
        "peg_volatility_7d": None,
    },
    "rocket-pool-reth": {
        "exploit_history_lst": 100,
        "market_cap": None,
        "dex_pool_depth": None,
        "eth_peg_deviation": None,
        "top_holder_concentration": None,
        "peg_volatility_7d": None,
    },
    "etherfi-eeth": {
        "exploit_history_lst": 100,
        "market_cap": None,
        "dex_pool_depth": None,
        "eth_peg_deviation": None,
        "top_holder_concentration": None,
        "peg_volatility_7d": None,
    },
}


def fetch_live_components(api_base: str, slug: str) -> dict | None:
    url = f"{api_base.rstrip('/')}/api/lsti/scores/{slug}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        raw = data.get("raw_values") or {}
        return {c: raw.get(c) for c in Q4_COMPONENTS}
    except Exception:
        return None


def build_row(api_base: str | None) -> dict:
    components = {}
    for peer in PEERS:
        values = None
        if api_base:
            values = fetch_live_components(api_base, peer["slug"])
        if values is None:
            values = FALLBACK_VALUES[peer["slug"]]
        components[peer["slug"]] = {
            "name": peer["name"],
            "symbol": peer["symbol"],
            "values": values,
        }
    return {
        "peers": components,
        "component_order": Q4_COMPONENTS,
        "component_meta": COMPONENT_META,
    }


def main() -> None:
    api_base = os.environ.get("BASIS_API_BASE")  # e.g. http://localhost:5000
    components_json = build_row(api_base)
    metadata = {
        "audit_path": "audits/lsti_rseth_audit_2026-04-20.md",
        "q4_components": Q4_COMPONENTS,
        "source_of_truth": "api.lsti.scores.raw_values" if api_base else "fallback",
        "captured_iso": datetime.now(timezone.utc).isoformat(),
    }

    execute(
        """
        INSERT INTO incident_snapshots (
            slug, event_date, title, summary, captured_at,
            components_json, metadata_json
        ) VALUES (%s, %s, %s, %s, NOW(), %s, %s)
        ON CONFLICT (slug) DO UPDATE SET
            event_date = EXCLUDED.event_date,
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            captured_at = NOW(),
            components_json = EXCLUDED.components_json,
            metadata_json = EXCLUDED.metadata_json,
            updated_at = NOW()
        """,
        (
            SLUG,
            EVENT_DATE,
            TITLE,
            SUMMARY,
            json.dumps(components_json, default=str),
            json.dumps(metadata, default=str),
        ),
    )
    print(f"Wrote incident_snapshots row for slug={SLUG}")


if __name__ == "__main__":
    main()
