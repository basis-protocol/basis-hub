"""
Crisis replay: Basis Cash (BAC) Failed Stable
Date: 2021-01-29
Index: sii
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("basis-cash")
    print(r)
