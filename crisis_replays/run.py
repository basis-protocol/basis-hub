"""
Crisis Replay — Reference Implementation
=========================================

Loads each replay's inputs.json + result.json, recomputes the input vector
hash and computation hash, and prints whether they match the persisted
values. No network calls, no DB. Anyone with this repo can run it.

Usage:
    python -m crisis_replays.run                # run every replay
    python -m crisis_replays.run terra-luna     # run a single replay
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path


REPLAY_ROOT = Path(__file__).resolve().parent


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


def list_replays() -> list[str]:
    return sorted(
        p.name for p in REPLAY_ROOT.iterdir()
        if p.is_dir() and (p / "inputs.json").exists() and (p / "result.json").exists()
    )


def verify(slug: str) -> dict:
    """Verify a single replay. Returns {slug, input_ok, computation_ok, ...}."""
    rdir = REPLAY_ROOT / slug
    if not rdir.exists():
        raise FileNotFoundError(f"No replay directory: {slug}")

    with (rdir / "inputs.json").open() as f:
        inputs = json.load(f)
    with (rdir / "result.json").open() as f:
        result = json.load(f)

    expected_input_hash = result.get("input_vector_hash")
    expected_comp_hash = result.get("computation_hash")
    method_version = result.get("methodology_version")
    final_score = result.get("final_score")
    final_grade = result.get("final_grade")

    actual_input_hash = canonical_hash(inputs)
    actual_comp_hash = canonical_hash({
        "input_hash": actual_input_hash,
        "methodology": method_version,
        "score": final_score,
        "grade": final_grade,
    })

    return {
        "slug": slug,
        "index_kind": result.get("index_kind"),
        "methodology_version": method_version,
        "final_score": final_score,
        "final_grade": final_grade,
        "input_ok": actual_input_hash == expected_input_hash,
        "computation_ok": actual_comp_hash == expected_comp_hash,
        "expected_input_hash": expected_input_hash,
        "actual_input_hash": actual_input_hash,
        "expected_computation_hash": expected_comp_hash,
        "actual_computation_hash": actual_comp_hash,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Replay crisis scoring runs")
    parser.add_argument("slug", nargs="?", help="Specific replay slug; omit to run all")
    args = parser.parse_args(argv)

    targets = [args.slug] if args.slug else list_replays()
    if not targets:
        print("No replays found in", REPLAY_ROOT)
        return 1

    failures = 0
    for slug in targets:
        try:
            r = verify(slug)
        except FileNotFoundError as e:
            print(f"  FAIL  {slug}: {e}")
            failures += 1
            continue
        marker = "OK  " if (r["input_ok"] and r["computation_ok"]) else "FAIL"
        if not (r["input_ok"] and r["computation_ok"]):
            failures += 1
        print(
            f"{marker}  {slug:<18}  {r['index_kind']:<4}  "
            f"score={r['final_score']:<6}  grade={r['final_grade']:<3}  "
            f"input_hash={r['actual_input_hash'][:14]}…  "
            f"comp_hash={r['actual_computation_hash'][:14]}…"
        )
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
