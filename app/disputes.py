"""
Dispute Infrastructure (Bucket A4)
===================================

Anyone may dispute a published score by referencing its hash. Each state
transition (submission, counter-evidence, resolution) is hashed off-chain
and the hash is anchored on Oracle V2 via `publishDisputeHash`.

The DB tracks four hashes per dispute:
    - score_hash_disputed   (the score the submitter is challenging)
    - submission_hash       (canonical hash of the submitter's payload)
    - counter_evidence_hash (Basis's reply, if any)
    - resolution_hash       (final adjudication payload)

Each hash is committed in its own row in `dispute_commitments`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)


VALID_STATUSES = {"open", "upheld", "rejected", "partially_upheld", "withdrawn"}
VALID_TRANSITIONS = ("submission", "counter_evidence", "resolution")


def _serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _hash_payload(kind: str, dispute_ref: str, payload: dict) -> str:
    canon = {"kind": kind, "dispute": dispute_ref, "payload": payload}
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), default=_serialize)
    return "0x" + hashlib.sha256(blob.encode()).hexdigest()


def submit_dispute(
    entity_slug: str,
    score_hash_disputed: str,
    submitter_address: str,
    submission_payload: dict,
    *,
    index_kind: str | None = None,
    score_value_disputed: float | None = None,
) -> dict:
    """Create a new dispute. Returns the row including computed submission hash."""
    if not entity_slug:
        raise ValueError("entity_slug required")
    if not score_hash_disputed:
        raise ValueError("score_hash_disputed required")
    if not submitter_address:
        raise ValueError("submitter_address required")
    if not isinstance(submission_payload, dict) or not submission_payload:
        raise ValueError("submission_payload must be a non-empty object")

    submission_ref = f"{entity_slug}:{score_hash_disputed}:{submitter_address}"
    submission_hash = _hash_payload("submission", submission_ref, submission_payload)

    row = fetch_one(
        """
        INSERT INTO disputes
            (entity_slug, index_kind, score_hash_disputed, score_value_disputed,
             submitter_address, submission_payload, submission_hash, submission_timestamp)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, NOW())
        RETURNING id, entity_slug, index_kind, score_hash_disputed,
                  submitter_address, submission_hash, submission_timestamp,
                  resolution_status
        """,
        (
            entity_slug,
            index_kind,
            score_hash_disputed,
            score_value_disputed,
            submitter_address,
            json.dumps(submission_payload, default=_serialize),
            submission_hash,
        ),
    )
    if not row:
        raise RuntimeError("Failed to insert dispute")

    execute(
        """
        INSERT INTO dispute_commitments
            (dispute_id, transition_kind, commitment_hash)
        VALUES (%s, %s, %s)
        """,
        (row["id"], "submission", submission_hash),
    )
    logger.info("dispute submitted id=%s entity=%s hash=%s",
                row["id"], entity_slug, submission_hash[:14])
    return dict(row)


def attach_counter_evidence(dispute_id: int, payload: dict) -> dict:
    """Record Basis's counter-evidence as a new state transition."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("counter_evidence payload must be non-empty")
    existing = fetch_one("SELECT id, entity_slug FROM disputes WHERE id = %s", (dispute_id,))
    if not existing:
        raise LookupError(f"Dispute {dispute_id} not found")

    ref = f"{existing['entity_slug']}:counter:{dispute_id}"
    h = _hash_payload("counter_evidence", ref, payload)
    execute(
        """
        UPDATE disputes
        SET counter_evidence_payload = %s::jsonb,
            counter_evidence_hash    = %s,
            counter_evidence_at      = NOW(),
            updated_at               = NOW()
        WHERE id = %s
        """,
        (json.dumps(payload, default=_serialize), h, dispute_id),
    )
    execute(
        """
        INSERT INTO dispute_commitments (dispute_id, transition_kind, commitment_hash)
        VALUES (%s, %s, %s)
        """,
        (dispute_id, "counter_evidence", h),
    )
    return {"dispute_id": dispute_id, "counter_evidence_hash": h}


def resolve_dispute(
    dispute_id: int,
    status: str,
    payload: dict,
    *,
    resolver: str | None = None,
) -> dict:
    """Set the final resolution. Status must be a terminal value."""
    if status not in VALID_STATUSES or status == "open":
        raise ValueError(f"resolution status must be one of {VALID_STATUSES - {'open'}}")
    if not isinstance(payload, dict) or not payload:
        raise ValueError("resolution payload must be non-empty")

    existing = fetch_one("SELECT id, entity_slug, resolution_status FROM disputes WHERE id = %s", (dispute_id,))
    if not existing:
        raise LookupError(f"Dispute {dispute_id} not found")
    if existing["resolution_status"] != "open":
        raise ValueError(f"Dispute {dispute_id} already resolved")

    ref = f"{existing['entity_slug']}:resolution:{dispute_id}"
    h = _hash_payload("resolution", ref, payload)
    execute(
        """
        UPDATE disputes
        SET resolution_status    = %s,
            resolution_payload   = %s::jsonb,
            resolution_hash      = %s,
            resolution_timestamp = NOW(),
            resolver             = %s,
            updated_at           = NOW()
        WHERE id = %s
        """,
        (status, json.dumps(payload, default=_serialize), h, resolver, dispute_id),
    )
    execute(
        """
        INSERT INTO dispute_commitments (dispute_id, transition_kind, commitment_hash)
        VALUES (%s, %s, %s)
        """,
        (dispute_id, "resolution", h),
    )
    return {"dispute_id": dispute_id, "resolution_hash": h, "status": status}


def get_dispute(dispute_id: int) -> dict | None:
    row = fetch_one("SELECT * FROM disputes WHERE id = %s", (dispute_id,))
    if not row:
        return None
    commits = fetch_all(
        """
        SELECT transition_kind, commitment_hash, on_chain_tx_hash,
               on_chain_chain, on_chain_block, committed_at
        FROM dispute_commitments
        WHERE dispute_id = %s
        ORDER BY committed_at ASC
        """,
        (dispute_id,),
    )
    out = dict(row)
    out["commitments"] = [dict(c) for c in (commits or [])]
    return out


def list_disputes(status: str | None = None, limit: int = 100) -> list[dict]:
    if status:
        rows = fetch_all(
            """
            SELECT id, entity_slug, index_kind, score_hash_disputed,
                   submitter_address, resolution_status,
                   submission_timestamp, resolution_timestamp
            FROM disputes
            WHERE resolution_status = %s
            ORDER BY submission_timestamp DESC
            LIMIT %s
            """,
            (status, limit),
        )
    else:
        rows = fetch_all(
            """
            SELECT id, entity_slug, index_kind, score_hash_disputed,
                   submitter_address, resolution_status,
                   submission_timestamp, resolution_timestamp
            FROM disputes
            ORDER BY submission_timestamp DESC
            LIMIT %s
            """,
            (limit,),
        )
    return [dict(r) for r in (rows or [])]


def pending_dispute_commits(limit: int = 50) -> list[dict]:
    return fetch_all(
        """
        SELECT id, dispute_id, transition_kind, commitment_hash
        FROM dispute_commitments
        WHERE on_chain_tx_hash IS NULL
        ORDER BY committed_at ASC
        LIMIT %s
        """,
        (limit,),
    )


def mark_dispute_commit_published(commit_id: int, tx_hash: str, chain: str, block: int | None) -> None:
    execute(
        """
        UPDATE dispute_commitments
        SET on_chain_tx_hash = %s, on_chain_chain = %s,
            on_chain_block = %s, committed_at = COALESCE(committed_at, NOW())
        WHERE id = %s
        """,
        (tx_hash, chain, block, commit_id),
    )
    execute(
        """
        UPDATE disputes
        SET on_chain_commit_tx = %s, on_chain_chain = %s,
            on_chain_committed_at = NOW(), updated_at = NOW()
        WHERE id = (SELECT dispute_id FROM dispute_commitments WHERE id = %s)
        """,
        (tx_hash, chain, commit_id),
    )
