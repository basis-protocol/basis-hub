#!/usr/bin/env python3
"""
One-time discovery script: find SPL Governance Realms matching
Drift, Jupiter, and Raydium on Solana mainnet via Helius RPC.

Usage:
    HELIUS_API_KEY=xxx python -m app.scripts.discover_solana_realms
"""

import json
import os
import sys
import requests

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
if not HELIUS_API_KEY:
    print("ERROR: HELIUS_API_KEY not set")
    sys.exit(1)

HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# SPL Governance program ID
SPL_GOVERNANCE_PROGRAM = "GovER5Lthms3bLBqWub97yVrMmEogzX7xNjdXpPPCVZw"

# Known Realm pubkeys to check directly (from Realms UI / community sources)
KNOWN_REALMS = {
    "Jupiter DAO": "5sGZEdn32y8nHax7TxEk3jXKszNT5YBrMKQJzHpnuMCB",
    "Drift DAO": "DriftGov1RGWYGBShFvpfeg5gy8bT7FN5Gxvr5poiJG",
    "Raydium": None,  # unknown — search for it
}

# Search terms
SEARCH_TERMS = ["jupiter", "drift", "raydium", "jup", "ray"]


def check_realm_account(pubkey: str, label: str):
    """Check if a specific pubkey is a valid Realm account."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [pubkey, {"encoding": "base64"}],
    }
    try:
        resp = requests.post(HELIUS_RPC_URL, json=payload, timeout=15)
        data = resp.json()
        value = data.get("result", {}).get("value")
        if value:
            owner = value.get("owner", "")
            data_len = len(value.get("data", [""])[0]) if value.get("data") else 0
            print(f"  ✓ {label} ({pubkey})")
            print(f"    Owner: {owner}")
            print(f"    Data length: {data_len} bytes (base64)")
            print(f"    Is SPL Governance: {owner == SPL_GOVERNANCE_PROGRAM}")
            return owner == SPL_GOVERNANCE_PROGRAM
        else:
            print(f"  ✗ {label} ({pubkey}) — account not found")
            return False
    except Exception as e:
        print(f"  ✗ {label} — error: {e}")
        return False


def search_governance_proposals(realm_pubkey: str, label: str):
    """Search for proposal accounts under a Realm via getProgramAccounts.

    SPL Governance proposal accounts (ProposalV2) have the Realm pubkey
    at byte offset 1 (after the account type discriminator byte).
    """
    import base64
    import struct
    from datetime import datetime, timezone

    # Account type discriminator for ProposalV2 = 6
    # Filter: first byte = 6, bytes 1..33 = realm pubkey
    realm_bytes = base64.b64decode(
        requests.post(HELIUS_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "getAccountInfo",
            "params": [realm_pubkey, {"encoding": "base64"}],
        }, timeout=15).json()["result"]["value"]["data"][0]
    )  # we don't actually need realm data, we need the pubkey bytes

    # Decode the realm pubkey to 32 bytes
    from base64 import b64encode
    import hashlib

    # Use memcmp filters on getProgramAccounts
    # ProposalV2 account layout: byte 0 = account_type (6), bytes 1-32 = governance pubkey
    # Actually, ProposalV2 layout: byte 0 = type(6), bytes 1-32 = governance, bytes 33-64 = governing_token_mint, bytes 65-96 = realm (NOT at offset 1)
    # Let's just get all proposals and filter client-side

    print(f"\n  Searching proposals for {label}...")

    # Simpler approach: use Helius enhanced transaction API to find recent governance txns
    # Or use getProgramAccounts with just the account type filter
    # For discovery, let's get a small sample

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getProgramAccounts",
        "params": [
            SPL_GOVERNANCE_PROGRAM,
            {
                "encoding": "base64",
                "filters": [
                    {"memcmp": {"offset": 0, "bytes": "7"}},  # ProposalV2 type = 6 (but encoded)
                ],
                "dataSlice": {"offset": 0, "length": 200},
            },
        ],
    }

    # This is too broad — will return ALL proposals across ALL realms
    # Better: filter by governance accounts that belong to our realm
    # For discovery, just report what we find about the realm
    print(f"  (Skipping broad proposal search — will use targeted approach in collector)")


def main():
    print("=" * 60)
    print("Solana SPL Governance Realm Discovery")
    print("=" * 60)

    print("\n1. Checking known Realm pubkeys...")
    for label, pubkey in KNOWN_REALMS.items():
        if pubkey:
            check_realm_account(pubkey, label)

    # Also try some well-known Jupiter governance addresses
    print("\n2. Checking additional known governance addresses...")
    extra_checks = [
        ("Jupiter Vote (known)", "jup7JGHgSBFhEVRJr85YCKnSCHF2qP8JFMfmGJyRCSa"),
        ("Jupiter DAO v2", "GoVERNANCEzz2LxUxyTFGsNxKYRhEfGPWJqY35cHAfYa"),
    ]
    for label, pubkey in extra_checks:
        check_realm_account(pubkey, label)

    # Try Realms public API
    print("\n3. Checking Realms public API...")
    try:
        # The Realms UI has a public API
        resp = requests.get(
            "https://app.realms.today/api/splGovernance/getRealms",
            timeout=15,
        )
        if resp.status_code == 200:
            realms = resp.json()
            print(f"  Found {len(realms)} total Realms")

            # Search for our protocols
            for term in SEARCH_TERMS:
                matches = [
                    r for r in realms
                    if term.lower() in json.dumps(r).lower()
                ]
                if matches:
                    print(f"\n  Matches for '{term}':")
                    for m in matches[:5]:
                        name = m.get("name", m.get("displayName", "unknown"))
                        pubkey = m.get("pubkey", m.get("realmId", "unknown"))
                        print(f"    - {name}: {pubkey}")
        else:
            print(f"  Realms API returned {resp.status_code}")
    except Exception as e:
        print(f"  Realms API error: {e}")

    # Try alternative Realms API endpoint
    print("\n4. Checking alternative Realms API endpoints...")
    alt_endpoints = [
        "https://governance-api.realms.today/api/splGovernance/getRealms",
        "https://realms-api-v2.vercel.app/api/realms",
    ]
    for url in alt_endpoints:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                count = len(data) if isinstance(data, list) else "?"
                print(f"  {url} → {count} realms")
                if isinstance(data, list):
                    for term in SEARCH_TERMS:
                        matches = [
                            r for r in data
                            if term.lower() in json.dumps(r).lower()
                        ]
                        if matches:
                            for m in matches[:3]:
                                print(f"    '{term}': {m.get('name', '?')} = {m.get('pubkey', '?')}")
                break
            else:
                print(f"  {url} → {resp.status_code}")
        except Exception as e:
            print(f"  {url} → {e}")

    print("\n" + "=" * 60)
    print("Discovery complete. Use results to populate SOLANA_GOVERNANCE_CONFIG")
    print("=" * 60)


if __name__ == "__main__":
    main()
