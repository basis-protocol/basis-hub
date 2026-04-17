# USDC / Silicon Valley Bank Depeg

**Date:** 2023-03-11
**Index:** `sii` (methodology `v1.0.0`)
**Entity:** `usdc`

USDC dropped to ~$0.87 after SVB exposure disclosed; recovered by Mar 13.

## Verification

```bash
python -m crisis_replays.run usdc-svb
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
