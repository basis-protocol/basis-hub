"""
Crisis replay: Celsius Network Withdrawal Freeze
Date: 2022-06-12
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("celsius")
    print(r)
