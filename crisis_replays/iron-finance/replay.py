"""
Crisis replay: Iron Finance / TITAN Bank Run
Date: 2021-06-16
Index: sii
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("iron-finance")
    print(r)
