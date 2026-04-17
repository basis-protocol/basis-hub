"""
Crisis replay: Wormhole Bridge Exploit
Date: 2022-02-02
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("wormhole")
    print(r)
