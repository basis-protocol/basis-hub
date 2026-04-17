"""
Crisis replay: FTX / Alameda Collapse
Date: 2022-11-08
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("ftx")
    print(r)
