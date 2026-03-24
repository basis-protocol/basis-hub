"""
Wallet Indexer — Configuration
==============================
Known stablecoin contracts: scored (from SII registry) and common unscored.
Size tier and coverage quality thresholds.
"""

from app.config import STABLECOIN_REGISTRY

# =============================================================================
# Scored stablecoins — built dynamically from the SII registry
# =============================================================================
# Map: lowercased contract address → { stablecoin_id, symbol, decimals }

SCORED_CONTRACTS = {}
for sid, cfg in STABLECOIN_REGISTRY.items():
    contract = cfg.get("contract", "")
    if contract:
        SCORED_CONTRACTS[contract.lower()] = {
            "stablecoin_id": sid,
            "symbol": cfg["symbol"],
            "decimals": cfg.get("decimals", 18),
            "name": cfg["name"],
        }

# =============================================================================
# Common unscored stablecoins — tracked in backlog
# =============================================================================

UNSCORED_CONTRACTS = {
    "0x40d16fc0246ad3160ccc09b8d0d3a2cd28ae6c2f": {
        "symbol": "GHO", "name": "GHO", "decimals": 18,
        "coingecko_id": "gho",
    },
    "0xf939e0a03fb07f59a73314e73794be0e57ac1b4e": {
        "symbol": "crvUSD", "name": "Curve USD", "decimals": 18,
        "coingecko_id": "crvusd",
    },
    "0x5f98805a4e8be255a32880fdec7f6728c6568ba0": {
        "symbol": "LUSD", "name": "Liquity USD", "decimals": 18,
        "coingecko_id": "liquity-usd",
    },
    "0x57ab1ec28d129707052df4df418d58a2d46d5f51": {
        "symbol": "sUSD", "name": "Synthetix USD", "decimals": 18,
        "coingecko_id": "susd",
    },
    "0x865377367054516e17014ccded1e7d814edc9ce4": {
        "symbol": "DOLA", "name": "Dola USD", "decimals": 18,
        "coingecko_id": "dola-usd",
    },
    "0x99d8a9c45b2eca8864373a26d1459e3dff1e17f3": {
        "symbol": "MIM", "name": "Magic Internet Money", "decimals": 18,
        "coingecko_id": "magic-internet-money",
    },
    "0xdb25f211ab05b1c97d595516f45d248390d6bfa5": {
        "symbol": "EURS", "name": "STASIS EURO", "decimals": 2,
        "coingecko_id": "stasis-eurs",
    },
    "0x8e870d67f660d95d5be530380d0ec0bd388289e1": {
        "symbol": "USDP", "name": "Pax Dollar", "decimals": 18,
        "coingecko_id": "paxos-standard",
    },
    "0x056fd409e1d7a124bd7017459dfea2f387b6d5cd": {
        "symbol": "GUSD", "name": "Gemini Dollar", "decimals": 2,
        "coingecko_id": "gemini-dollar",
    },
    "0x03ab458634910aad20ef5f1c8ee96f1d6ac54919": {
        "symbol": "RAI", "name": "Rai Reflex Index", "decimals": 18,
        "coingecko_id": "rai",
    },
}

# Combined lookup: all known stablecoin contracts (lowercased)
ALL_KNOWN_CONTRACTS = {**SCORED_CONTRACTS, **UNSCORED_CONTRACTS}

# =============================================================================
# Thresholds
# =============================================================================

SIZE_TIER_THRESHOLDS = [
    (10_000_000, "whale"),
    (100_000, "institutional"),
    (0, "retail"),
]

COVERAGE_QUALITY_THRESHOLDS = [
    (0.0, "full"),
    (10.0, "high"),
    (40.0, "partial"),
]
# anything > 40% → "low"

FORMULA_VERSION = "wallet-v1.0.0"

ETHERSCAN_RATE_LIMIT_DELAY = 0.11  # ~9 req/sec (Standard tier: 10/sec)


def classify_size_tier(total_value: float) -> str:
    """Classify wallet by total stablecoin value."""
    for threshold, tier in SIZE_TIER_THRESHOLDS:
        if total_value >= threshold:
            return tier
    return "retail"


def classify_coverage(unscored_pct: float) -> str:
    """Classify coverage quality by unscored percentage."""
    for threshold, quality in COVERAGE_QUALITY_THRESHOLDS:
        if unscored_pct <= threshold:
            return quality
    return "low"
