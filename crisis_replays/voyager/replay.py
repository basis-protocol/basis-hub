"""
Crisis replay: Voyager Digital Insolvency
Date: 2022-07-01
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("voyager")
    print(r)
