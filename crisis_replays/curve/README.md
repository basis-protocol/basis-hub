# Curve Pools Vyper Reentrancy

**Date:** 2023-07-30
**Index:** `psi` (methodology `v0.2.0`)
**Entity:** `curve`

Vyper compiler reentrancy bug drained four CRV pools.

## Verification

```bash
python -m crisis_replays.run curve
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
