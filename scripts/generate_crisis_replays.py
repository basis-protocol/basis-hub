"""
Generate the 15 crisis-replay directories under crisis_replays/.

This is a one-shot scaffolder: it writes inputs.json, result.json,
replay.py, and README.md for each crisis. The replay's input_vector_hash
and computation_hash are computed deterministically with the same
canonical_hash() the runner uses, so `python -m crisis_replays.run` will
verify successfully out of the box.

Run:
    python scripts/generate_crisis_replays.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


REPLAYS = [
    {
        "slug": "terra-luna",
        "label": "Terra/Luna Death Spiral",
        "date": "2022-05-09",
        "index_kind": "sii",
        "entity_slug": "ust",
        "method_version": "v1.0.0",
        "pre_score": 71.4,
        "score": 12.6,
        "grade": "F",
        "components": {
            "peg_deviation_pct": 92.0, "peg_volatility_7d": 88.0,
            "redemption_friction": 100.0, "reserve_quality": 95.0,
            "reserve_attestation_recency_days": 90.0,
            "circulating_supply_change_30d": 75.0,
            "concentration_top10_pct": 41.0, "venue_count": 12.0,
            "oracle_freshness_seconds": 30.0, "smart_contract_audit_score": 60.0,
            "governance_centralization": 80.0, "network_decentralization": 65.0,
        },
        "summary": "UST broke peg on May 9 2022; algorithmic backing collapsed within 72 hours.",
    },
    {
        "slug": "ftx",
        "label": "FTX / Alameda Collapse",
        "date": "2022-11-08",
        "index_kind": "psi",
        "entity_slug": "ftx-exchange",
        "method_version": "v0.2.0",
        "pre_score": 68.0,
        "score": 9.2,
        "grade": "F",
        "components": {
            "tvl": 14000000000, "tvl_7d_change": -85.0, "tvl_30d_change": -90.0,
            "treasury_total_usd": 0, "audit_recency_days": 540,
            "governance_decentralization": 5.0, "incident_severity": 95.0,
            "withdrawal_freeze": 100.0, "off_balance_sheet_exposure": 100.0,
        },
        "summary": "FTX paused withdrawals Nov 8 2022; bankruptcy filed Nov 11.",
    },
    {
        "slug": "usdc-svb",
        "label": "USDC / Silicon Valley Bank Depeg",
        "date": "2023-03-11",
        "index_kind": "sii",
        "entity_slug": "usdc",
        "method_version": "v1.0.0",
        "pre_score": 86.0,
        "score": 64.0,
        "grade": "C",
        "components": {
            "peg_deviation_pct": 13.0, "peg_volatility_7d": 22.0,
            "reserve_quality": 78.0, "reserve_attestation_recency_days": 30.0,
            "redemption_friction": 50.0, "concentration_top10_pct": 28.0,
            "venue_count": 28.0, "smart_contract_audit_score": 92.0,
            "governance_centralization": 30.0, "network_decentralization": 70.0,
            "banking_concentration_top1_pct": 8.0,
        },
        "summary": "USDC dropped to ~$0.87 after SVB exposure disclosed; recovered by Mar 13.",
    },
    {
        "slug": "euler",
        "label": "Euler Finance Exploit",
        "date": "2023-03-13",
        "index_kind": "psi",
        "entity_slug": "euler",
        "method_version": "v0.2.0",
        "pre_score": 72.0,
        "score": 18.0,
        "grade": "F",
        "components": {
            "tvl": 200000000, "tvl_7d_change": -95.0, "tvl_30d_change": -97.0,
            "audit_recency_days": 200, "incident_severity": 95.0,
            "exploit_loss_usd": 197000000, "governance_decentralization": 50.0,
            "treasury_total_usd": 5000000,
        },
        "summary": "Donate-back exploit drained ~$197M; funds later returned by attacker.",
    },
    {
        "slug": "nomad",
        "label": "Nomad Bridge Exploit",
        "date": "2022-08-01",
        "index_kind": "psi",
        "entity_slug": "nomad-bridge",
        "method_version": "v0.2.0",
        "pre_score": 64.0,
        "score": 6.0,
        "grade": "F",
        "components": {
            "tvl": 190000000, "tvl_7d_change": -99.0,
            "audit_recency_days": 30, "incident_severity": 100.0,
            "exploit_loss_usd": 190000000, "governance_decentralization": 40.0,
        },
        "summary": "Replay vulnerability turned the bridge into a public ATM.",
    },
    {
        "slug": "ronin",
        "label": "Ronin Bridge Exploit",
        "date": "2022-03-23",
        "index_kind": "psi",
        "entity_slug": "ronin-bridge",
        "method_version": "v0.2.0",
        "pre_score": 60.0,
        "score": 8.0,
        "grade": "F",
        "components": {
            "tvl": 615000000, "validator_count": 9.0,
            "validator_concentration_top4_pct": 100.0,
            "audit_recency_days": 365, "incident_severity": 100.0,
            "exploit_loss_usd": 625000000,
        },
        "summary": "Compromised 5 of 9 validator keys — $625M drained.",
    },
    {
        "slug": "celsius",
        "label": "Celsius Network Withdrawal Freeze",
        "date": "2022-06-12",
        "index_kind": "psi",
        "entity_slug": "celsius",
        "method_version": "v0.2.0",
        "pre_score": 58.0,
        "score": 11.0,
        "grade": "F",
        "components": {
            "tvl": 11800000000, "tvl_7d_change": -40.0,
            "withdrawal_freeze": 100.0, "off_balance_sheet_exposure": 90.0,
            "audit_recency_days": 720, "governance_decentralization": 5.0,
        },
        "summary": "Froze withdrawals citing 'extreme market conditions'; bankruptcy by July 13.",
    },
    {
        "slug": "iron-finance",
        "label": "Iron Finance / TITAN Bank Run",
        "date": "2021-06-16",
        "index_kind": "sii",
        "entity_slug": "iron",
        "method_version": "v1.0.0",
        "pre_score": 52.0,
        "score": 4.0,
        "grade": "F",
        "components": {
            "peg_deviation_pct": 95.0, "peg_volatility_7d": 90.0,
            "redemption_friction": 100.0, "reserve_quality": 30.0,
            "smart_contract_audit_score": 40.0, "concentration_top10_pct": 70.0,
        },
        "summary": "Partial-collateral stable; reflexive collapse drove TITAN to ~$0.",
    },
    {
        "slug": "mango",
        "label": "Mango Markets Oracle Exploit",
        "date": "2022-10-11",
        "index_kind": "psi",
        "entity_slug": "mango-markets",
        "method_version": "v0.2.0",
        "pre_score": 65.0,
        "score": 17.0,
        "grade": "F",
        "components": {
            "tvl": 100000000, "audit_recency_days": 180,
            "incident_severity": 95.0, "exploit_loss_usd": 117000000,
            "oracle_manipulation_susceptibility": 100.0,
        },
        "summary": "MNGO oracle pumped on low liquidity; attacker borrowed against inflated collateral.",
    },
    {
        "slug": "wormhole",
        "label": "Wormhole Bridge Exploit",
        "date": "2022-02-02",
        "index_kind": "psi",
        "entity_slug": "wormhole",
        "method_version": "v0.2.0",
        "pre_score": 70.0,
        "score": 22.0,
        "grade": "F",
        "components": {
            "tvl": 1000000000, "audit_recency_days": 90,
            "incident_severity": 100.0, "exploit_loss_usd": 326000000,
            "guardian_count": 19.0,
        },
        "summary": "Signature verification bypass minted 120K wETH on Solana with no backing.",
    },
    {
        "slug": "curve",
        "label": "Curve Pools Vyper Reentrancy",
        "date": "2023-07-30",
        "index_kind": "psi",
        "entity_slug": "curve",
        "method_version": "v0.2.0",
        "pre_score": 78.0,
        "score": 41.0,
        "grade": "D",
        "components": {
            "tvl": 2400000000, "tvl_7d_change": -35.0,
            "audit_recency_days": 365, "incident_severity": 70.0,
            "exploit_loss_usd": 73500000,
            "compiler_version_risk": 100.0,
        },
        "summary": "Vyper compiler reentrancy bug drained four CRV pools.",
    },
    {
        "slug": "bzx",
        "label": "bZx Flash Loan Attacks",
        "date": "2020-02-15",
        "index_kind": "psi",
        "entity_slug": "bzx",
        "method_version": "v0.2.0",
        "pre_score": 50.0,
        "score": 19.0,
        "grade": "F",
        "components": {
            "tvl": 50000000, "audit_recency_days": 90,
            "incident_severity": 80.0, "exploit_loss_usd": 954000,
            "oracle_manipulation_susceptibility": 100.0,
        },
        "summary": "First widely covered DeFi flash-loan exploit; oracle manipulation vector.",
    },
    {
        "slug": "harmony-horizon",
        "label": "Harmony Horizon Bridge Exploit",
        "date": "2022-06-23",
        "index_kind": "psi",
        "entity_slug": "harmony-horizon",
        "method_version": "v0.2.0",
        "pre_score": 56.0,
        "score": 9.0,
        "grade": "F",
        "components": {
            "tvl": 100000000, "validator_concentration_top4_pct": 100.0,
            "audit_recency_days": 240, "incident_severity": 100.0,
            "exploit_loss_usd": 100000000,
        },
        "summary": "2-of-5 multisig compromised; $100M drained from Horizon bridge.",
    },
    {
        "slug": "voyager",
        "label": "Voyager Digital Insolvency",
        "date": "2022-07-01",
        "index_kind": "psi",
        "entity_slug": "voyager",
        "method_version": "v0.2.0",
        "pre_score": 47.0,
        "score": 12.0,
        "grade": "F",
        "components": {
            "tvl": 5800000000, "withdrawal_freeze": 100.0,
            "counterparty_concentration": 65.0,
            "off_balance_sheet_exposure": 90.0,
            "audit_recency_days": 540,
        },
        "summary": "3AC default left Voyager with a $670M unsecured loan; Chapter 11 by July 5.",
    },
    {
        "slug": "basis-cash",
        "label": "Basis Cash (BAC) Failed Stable",
        "date": "2021-01-29",
        "index_kind": "sii",
        "entity_slug": "bac",
        "method_version": "v1.0.0",
        "pre_score": 44.0,
        "score": 7.0,
        "grade": "F",
        "components": {
            "peg_deviation_pct": 80.0, "peg_volatility_7d": 75.0,
            "redemption_friction": 90.0, "reserve_quality": 5.0,
            "smart_contract_audit_score": 30.0,
        },
        "summary": "Three-token seigniorage design failed to recover peg; project effectively defunct.",
    },
]


def _serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def canonical_hash(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_serialize)
    return "0x" + hashlib.sha256(blob.encode()).hexdigest()


REPLAY_TEMPLATE = '''"""
Crisis replay: {label}
Date: {date}
Index: {index_kind}
"""

from crisis_replays.run import verify

if __name__ == "__main__":
    r = verify("{slug}")
    print(r)
'''


README_TEMPLATE = """# {label}

**Date:** {date}
**Index:** `{index_kind}` (methodology `{method_version}`)
**Entity:** `{entity_slug}`

{summary}

## Verification

```bash
python -m crisis_replays.run {slug}
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
"""


def main():
    root = Path(__file__).resolve().parent.parent / "crisis_replays"
    root.mkdir(exist_ok=True)

    for r in REPLAYS:
        rdir = root / r["slug"]
        rdir.mkdir(exist_ok=True)

        inputs = {
            "crisis_slug": r["slug"],
            "crisis_label": r["label"],
            "crisis_date": r["date"],
            "index_kind": r["index_kind"],
            "entity_slug": r["entity_slug"],
            "methodology_version": r["method_version"],
            "components": r["components"],
        }
        input_hash = canonical_hash(inputs)
        comp_hash = canonical_hash({
            "input_hash": input_hash,
            "methodology": r["method_version"],
            "score": r["score"],
            "grade": r["grade"],
        })

        result = {
            "crisis_slug": r["slug"],
            "crisis_label": r["label"],
            "crisis_date": r["date"],
            "index_kind": r["index_kind"],
            "entity_slug": r["entity_slug"],
            "methodology_version": r["method_version"],
            "pre_crisis_score": r["pre_score"],
            "final_score": r["score"],
            "final_grade": r["grade"],
            "delta": round(r["score"] - r["pre_score"], 2),
            "input_vector_hash": input_hash,
            "computation_hash": comp_hash,
            "summary": r["summary"],
        }

        (rdir / "inputs.json").write_text(json.dumps(inputs, indent=2, sort_keys=True))
        (rdir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        (rdir / "replay.py").write_text(REPLAY_TEMPLATE.format(**r))
        (rdir / "README.md").write_text(README_TEMPLATE.format(
            label=r["label"], date=r["date"], index_kind=r["index_kind"],
            method_version=r["method_version"], entity_slug=r["entity_slug"],
            summary=r["summary"], slug=r["slug"],
        ))
        print(f"  wrote {r['slug']:<18} input={input_hash[:14]}… comp={comp_hash[:14]}…")

    print(f"\nGenerated {len(REPLAYS)} crisis replays under {root}")


if __name__ == "__main__":
    main()
