# Harmony Horizon Bridge Exploit

**Date:** 2022-06-23
**Index:** `psi` (methodology `v0.2.0`)
**Entity:** `harmony-horizon`

2-of-5 multisig compromised; $100M drained from Horizon bridge.

## Verification

```bash
python -m crisis_replays.run harmony-horizon
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
