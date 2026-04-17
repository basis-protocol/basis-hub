"""
Crisis replay: Ronin Bridge Exploit
Date: 2022-03-23
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("ronin")
    print(r)
