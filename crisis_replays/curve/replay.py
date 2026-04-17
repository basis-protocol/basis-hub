"""
Crisis replay: Curve Pools Vyper Reentrancy
Date: 2023-07-30
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("curve")
    print(r)
