"""
Crisis replay: USDC / Silicon Valley Bank Depeg
Date: 2023-03-11
Index: sii
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("usdc-svb")
    print(r)
