"""
Static configuration — stablecoin mints, protocol programs, grade mappings.
Add new entries here, not scattered through code.
"""

import os

BASIS_API_URL = os.environ.get("BASIS_API_URL", "https://basisprotocol.xyz")

# Solana mint address => Basis coin ID
STABLECOIN_MINTS: dict[str, str] = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "usdc",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "usdt",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "dai",
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo": "pyusd",
}

# Solana program ID => Basis protocol slug
PROTOCOL_PROGRAMS: dict[str, str] = {
    "dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH": "drift",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "jupiter-perpetual-exchange",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "raydium",
}

GRADE_EMOJI: dict[str, str] = {
    "A+": "\U0001f7e2", "A": "\U0001f7e2", "A-": "\U0001f7e2",
    "B+": "\U0001f7e1", "B": "\U0001f7e1", "B-": "\U0001f7e1",
    "C+": "\U0001f7e0", "C": "\U0001f7e0", "C-": "\U0001f7e0",
    "D+": "\U0001f534", "D": "\U0001f534", "D-": "\U0001f534",
    "F": "\u26d4",
}

# CQI grade bands (0-100 scale)
GRADE_THRESHOLDS: list[tuple[float, str]] = [
    (90, "A+"), (85, "A"), (80, "A-"),
    (75, "B+"), (70, "B"), (65, "B-"),
    (60, "C+"), (55, "C"), (50, "C-"),
    (45, "D+"), (40, "D"), (35, "D-"),
]
