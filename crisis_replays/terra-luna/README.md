# Terra/Luna Death Spiral

**Date:** 2022-05-09
**Index:** `sii` (methodology `v1.0.0`)
**Entity:** `ust`

UST broke peg on May 9 2022; algorithmic backing collapsed within 72 hours.

## Verification

```bash
python -m crisis_replays.run terra-luna
```

The runner recomputes:

  - `input_vector_hash = sha256(canonical(inputs.json))`
  - `computation_hash  = sha256(input_vector_hash || methodology || score || grade)`

and prints `OK` if both match the values pinned in `result.json`.

## Files

- `inputs.json` — the input vector (component values applied at the moment of the event)
- `result.json` — the methodology-pinned final score, grade, delta, and hashes
- `replay.py`   — convenience entry-point; calls `crisis_replays.run.verify`
