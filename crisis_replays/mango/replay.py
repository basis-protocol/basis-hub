"""
Crisis replay: Mango Markets Oracle Exploit
Date: 2022-10-11
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("mango")
    print(r)
