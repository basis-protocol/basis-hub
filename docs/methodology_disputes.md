# Disputes — Methodology

This document is the public contract for how Basis handles disputes
against published scores.

## Who can dispute?

Anyone with an Ethereum address. There is no whitelist, no minimum
stake, and no fee at the protocol layer. The on-chain commitment is
write-once per `(disputeId, transitionKind)` so spam is naturally
limited by gas.

## What can be disputed?

Any score that has been published with a content hash. That includes
SII, PSI, RPI, and CQI scores, as well as wallet risk scores. The
submitter must reference the score by its hash, not by the entity name
or score value, to bind the dispute to a specific computation.

## Lifecycle

1. **Submission** — `POST /api/disputes` with:
   - `entity_slug`             (which entity is being scored)
   - `score_hash_disputed`     (the score the submitter is challenging)
   - `submitter_address`       (the submitter's Ethereum address)
   - `submission_payload`      (the claim, in JSON; arbitrary structure)
   - `index_kind` (optional)
   - `score_value_disputed` (optional, for display)

   The hub canonicalizes the payload, computes
   `submission_hash = sha256(canonical(submission))`, persists the row,
   and returns the new dispute id and submission hash.

2. **Counter-evidence** — Basis can attach evidence that confirms or
   refutes the claim. Hashed exactly like the submission and stored in
   `counter_evidence_hash`.

3. **Resolution** — A terminal status (`upheld`, `rejected`,
   `partially_upheld`, or `withdrawn`) plus a payload explaining the
   adjudication. Hashed and stored in `resolution_hash`.

Each transition writes its own row in `dispute_commitments`. The keeper
sweeps that table on every cycle and anchors the hashes on Oracle V2 via
`publishDisputeHash(disputeId, transitionKind, commitmentHash)`.

The on-chain commitments are write-once per `(disputeId, transitionKind)`,
so the chain is the canonical audit trail. If the off-chain DB ever
diverges from what is on-chain, the chain wins.

## Verifying

Given a dispute id, anyone can:

1. Fetch `GET /api/disputes/{id}` to read the full state and the four
   hashes (score_hash_disputed, submission_hash, counter_evidence_hash,
   resolution_hash).
2. Recompute each hash from the canonical payload returned by the API.
3. Look up `getDisputeCommitment(disputeId, transitionKind)` on the
   Oracle contract to confirm the hash was anchored.
4. The block timestamp on the on-chain commitment is the canonical
   "when did Basis claim this happened?" answer.

## Hash construction

```
canonical(payload) = json.dumps(
    {"kind": <transition>, "dispute": <ref>, "payload": <body>},
    sort_keys=True, separators=(",", ":")
)
hash = "0x" + sha256(canonical(payload)).hexdigest()
```

Identical to the construction used by `app/computation_attestation.py`.

## On-chain identifiers

The `disputeId` written on-chain is `keccak256("dispute:{db_id}")`.
The `transitionKind` is one of:

  - `"SUBM"` — submission
  - `"CTRE"` — counter-evidence
  - `"RSLV"` — resolution

both encoded as `bytes4`.
