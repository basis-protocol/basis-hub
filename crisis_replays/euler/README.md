# Euler Finance Exploit

**Date:** 2023-03-13
**Index:** `psi` (methodology `v0.2.0`)
**Entity:** `euler`

Donate-back exploit drained ~$197M; funds later returned by attacker.

## Verification

```bash
python -m crisis_replays.run euler
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
