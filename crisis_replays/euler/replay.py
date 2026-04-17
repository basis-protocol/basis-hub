"""
Crisis replay: Euler Finance Exploit
Date: 2023-03-13
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("euler")
    print(r)
