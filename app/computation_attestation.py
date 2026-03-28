"""
Computation Attestation — Input Hash Utility
==============================================
Computes a deterministic hash of all inputs to a score computation.
Used for retroactive verification: given these inputs, this score was produced.
"""

import hashlib
import json
from datetime import datetime


def compute_inputs_hash(component_scores, wallet_holdings, formula_version):
    """
    Compute a deterministic hash of all inputs to a score computation.

    Args:
        component_scores: dict of component_id -> normalized score
        wallet_holdings: list of dicts with symbol, value_usd, sii_score
        formula_version: string version identifier

    Returns:
        tuple of (hash_string, summary_dict)
    """
    inputs = {
        "component_scores": {k: v for k, v in sorted(component_scores.items()) if v is not None},
        "holdings": sorted([
            {"symbol": h.get("symbol", ""), "value_usd": h.get("value_usd", 0), "sii_score": h.get("sii_score")}
            for h in wallet_holdings
        ], key=lambda x: x["symbol"]),
        "formula_version": formula_version,
        "computed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    }

    canonical = json.dumps(inputs, sort_keys=True, separators=(',', ':'))
    hash_val = '0x' + hashlib.sha256(canonical.encode()).hexdigest()

    summary = {
        "components_count": len(inputs["component_scores"]),
        "holdings_count": len(inputs["holdings"]),
        "formula_version": formula_version,
        "computed_at": inputs["computed_at"]
    }

    return hash_val, summary
