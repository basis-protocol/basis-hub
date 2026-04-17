"""
Crisis replay: Harmony Horizon Bridge Exploit
Date: 2022-06-23
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("harmony-horizon")
    print(r)
