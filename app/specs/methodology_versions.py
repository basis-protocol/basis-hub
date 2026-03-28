"""
Methodology version registry for SII and Wallet risk scoring.
Provides version metadata, governance rules, and changelog.
"""

METHODOLOGY_VERSIONS = {
    "current": "v1.0.0",
    "versions": [
        {
            "version": "v1.0.0",
            "released": "2025-12-28",
            "status": "current",
            "formula": "SII = 0.30*Peg + 0.25*Liquidity + 0.15*MintBurn + 0.10*Distribution + 0.20*Structural",
            "changelog": "Initial public release"
        }
    ],
    "governance": {
        "change_protocol": "Announced 30 days in advance. Versioned. Timestamped. Retroactively reproducible.",
        "comment_period_days": 30,
        "deprecation_notice_days": 90
    }
}

WALLET_METHODOLOGY_VERSIONS = {
    "current": "wallet-v1.0.0",
    "versions": [
        {
            "version": "wallet-v1.0.0",
            "released": "2026-03-01",
            "status": "current",
            "formula": "Value-weighted average SII across wallet holdings",
            "changelog": "Initial wallet risk scoring"
        }
    ]
}
