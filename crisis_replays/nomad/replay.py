"""
Crisis replay: Nomad Bridge Exploit
Date: 2022-08-01
Index: psi
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("nomad")
    print(r)
