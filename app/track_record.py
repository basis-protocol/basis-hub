"""
Track Record Commitments (Bucket A1)
=====================================

Detects consequential events the platform makes a "call" on, hashes them
into a canonical event payload, persists them in `track_record_commitments`,
and surfaces a queue of pending commits for the keeper to anchor on-chain.

Trigger conditions (from the sprint spec):

  - divergence signal       (any new row in `divergence_events` or
                             surface emitted by `app/divergence.py`)
  - rpi_delta > 10           (week-over-week absolute change for any RPI score)
  - coherence drop           (latest coherence_reports row with status != 'pass')
  - score_change > 5         (SII or PSI absolute delta vs prior cycle)

Outcome scoring runs on every cycle for events that have aged past the
30/60/90 day windows. The outcome is the absolute change in the entity's
score from the event_timestamp to the horizon, signed in the direction
of the original call (so positive = call was right, negative = wrong).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)


EVENT_TYPES = ("divergence", "rpi_delta", "coherence_drop", "score_change")


def _serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def canonical_event_hash(event_type: str, entity_slug: str, payload: dict) -> str:
    """SHA-256 of canonical (event_type, entity_slug, sorted payload)."""
    canon = {
        "event_type": event_type,
        "entity_slug": entity_slug,
        "payload": payload,
    }
    blob = json.dumps(canon, sort_keys=True, separators=(",", ":"), default=_serialize)
    return "0x" + hashlib.sha256(blob.encode()).hexdigest()


def _latest_state_root_hash() -> str | None:
    """Return the keccak-style hash of the latest pulse state root, if any."""
    row = fetch_one(
        """
        SELECT summary FROM daily_pulses
        ORDER BY pulse_date DESC LIMIT 1
        """
    )
    if not row:
        return None
    summary = row.get("summary")
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except Exception:
            summary = None
    if not isinstance(summary, dict):
        return None
    state_root = summary.get("state_root")
    if not state_root:
        return None
    canon = json.dumps(state_root, sort_keys=True, separators=(",", ":"), default=_serialize)
    return "0x" + hashlib.sha256(canon.encode()).hexdigest()


def record_event(
    event_type: str,
    entity_slug: str,
    payload: dict,
    *,
    event_timestamp: datetime | None = None,
    magnitude: float | None = None,
    direction: str | None = None,
    score_before: float | None = None,
    score_after: float | None = None,
    methodology_version: str | None = None,
    notes: str | None = None,
) -> dict | None:
    """Persist a track-record event. Idempotent on event_hash."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type: {event_type}")
    ts = event_timestamp or datetime.now(timezone.utc)
    event_hash = canonical_event_hash(event_type, entity_slug, payload)
    state_root = _latest_state_root_hash()

    existing = fetch_one(
        "SELECT id FROM track_record_commitments WHERE event_hash = %s",
        (event_hash,),
    )
    if existing:
        return None

    row = fetch_one(
        """
        INSERT INTO track_record_commitments
            (event_type, entity_slug, event_payload, event_hash, event_timestamp,
             magnitude, direction, score_before, score_after,
             state_root_at_event, methodology_version, notes)
        VALUES (%s, %s, %s::jsonb, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s)
        ON CONFLICT (event_hash) DO NOTHING
        RETURNING id
        """,
        (
            event_type,
            entity_slug,
            json.dumps(payload, default=_serialize),
            event_hash,
            ts,
            magnitude,
            direction,
            score_before,
            score_after,
            state_root,
            methodology_version,
            notes,
        ),
    )
    if row:
        logger.info(
            "track_record: %s/%s magnitude=%s hash=%s",
            event_type, entity_slug, magnitude, event_hash[:14],
        )
    return row


def detect_score_change_events(min_delta: float = 5.0, lookback_hours: int = 6) -> int:
    """SII score change > min_delta points vs prior cycle."""
    rows = fetch_all(
        """
        SELECT s.coingecko_id AS slug, s.overall_score AS current_score,
               s.computed_at AS computed_at,
               (
                   SELECT prev.overall_score
                   FROM scores prev
                   WHERE prev.coingecko_id = s.coingecko_id
                     AND prev.computed_at < s.computed_at
                   ORDER BY prev.computed_at DESC LIMIT 1
               ) AS prev_score
        FROM scores s
        WHERE s.computed_at > NOW() - INTERVAL '%s hours'
        """ % int(lookback_hours)
    )
    count = 0
    for r in rows or []:
        cur = r.get("current_score")
        prev = r.get("prev_score")
        if cur is None or prev is None:
            continue
        delta = float(cur) - float(prev)
        if abs(delta) < min_delta:
            continue
        payload = {
            "index": "sii",
            "current_score": float(cur),
            "previous_score": float(prev),
            "delta": delta,
            "computed_at": r.get("computed_at"),
        }
        if record_event(
            "score_change",
            r["slug"],
            payload,
            event_timestamp=r.get("computed_at"),
            magnitude=abs(delta),
            direction="up" if delta > 0 else "down",
            score_before=float(prev),
            score_after=float(cur),
        ):
            count += 1
    return count


def detect_rpi_delta_events(min_delta: float = 10.0, lookback_days: int = 7) -> int:
    """RPI week-over-week absolute change > min_delta points."""
    try:
        rows = fetch_all(
            """
            SELECT protocol_slug AS slug, score AS current_score, computed_at,
                   (
                       SELECT prev.score FROM rpi_scores prev
                       WHERE prev.protocol_slug = r.protocol_slug
                         AND prev.computed_at < r.computed_at - INTERVAL '%s days'
                       ORDER BY prev.computed_at DESC LIMIT 1
                   ) AS prev_score
            FROM rpi_scores r
            WHERE r.computed_at > NOW() - INTERVAL '24 hours'
            """ % int(lookback_days)
        )
    except Exception as exc:
        logger.debug("rpi_delta detection skipped: %s", exc)
        return 0

    count = 0
    for r in rows or []:
        cur = r.get("current_score")
        prev = r.get("prev_score")
        if cur is None or prev is None:
            continue
        delta = float(cur) - float(prev)
        if abs(delta) < min_delta:
            continue
        payload = {
            "index": "rpi",
            "current_score": float(cur),
            "previous_score": float(prev),
            "delta": delta,
            "lookback_days": lookback_days,
            "computed_at": r.get("computed_at"),
        }
        if record_event(
            "rpi_delta",
            r["slug"],
            payload,
            event_timestamp=r.get("computed_at"),
            magnitude=abs(delta),
            direction="up" if delta > 0 else "down",
            score_before=float(prev),
            score_after=float(cur),
        ):
            count += 1
    return count


def detect_coherence_drops(lookback_hours: int = 30) -> int:
    """Any coherence_reports row in the lookback window with non-pass status."""
    try:
        rows = fetch_all(
            """
            SELECT * FROM coherence_reports
            WHERE created_at > NOW() - INTERVAL '%s hours'
            """ % int(lookback_hours)
        )
    except Exception as exc:
        logger.debug("coherence detection skipped: %s", exc)
        return 0

    count = 0
    for r in rows or []:
        status = (r.get("status") or "").lower()
        if status in ("pass", "ok", ""):
            continue
        slug = r.get("check_name") or r.get("domain") or "system"
        payload = {
            "report_id": r.get("id"),
            "status": status,
            "check_name": r.get("check_name"),
            "domain": r.get("domain"),
            "details": r.get("details"),
            "created_at": r.get("created_at"),
        }
        if record_event(
            "coherence_drop",
            slug,
            payload,
            event_timestamp=r.get("created_at"),
            magnitude=None,
            direction="down",
        ):
            count += 1
    return count


def detect_divergence_signals(lookback_hours: int = 24) -> int:
    """Treat any new deviation_events row as a divergence signal."""
    try:
        rows = fetch_all(
            """
            SELECT id, coingecko_id AS slug, event_start, event_end,
                   max_deviation_pct, avg_deviation_pct, direction, recovery_complete
            FROM deviation_events
            WHERE event_start > NOW() - INTERVAL '%s hours'
            """ % int(lookback_hours)
        )
    except Exception as exc:
        logger.debug("divergence detection skipped: %s", exc)
        return 0

    count = 0
    for r in rows or []:
        payload = {
            "deviation_event_id": r.get("id"),
            "max_deviation_pct": r.get("max_deviation_pct"),
            "avg_deviation_pct": r.get("avg_deviation_pct"),
            "direction": r.get("direction"),
            "recovery_complete": r.get("recovery_complete"),
            "event_start": r.get("event_start"),
            "event_end": r.get("event_end"),
        }
        if record_event(
            "divergence",
            r["slug"],
            payload,
            event_timestamp=r.get("event_start"),
            magnitude=float(r.get("max_deviation_pct") or 0),
            direction=r.get("direction"),
        ):
            count += 1
    return count


def detect_all() -> dict[str, int]:
    """Run every detector. Returns counts per event_type."""
    return {
        "divergence": detect_divergence_signals(),
        "rpi_delta": detect_rpi_delta_events(),
        "coherence_drop": detect_coherence_drops(),
        "score_change": detect_score_change_events(),
    }


# ─── Outcome scoring ──────────────────────────────────────────────────────

def _score_at(slug: str, when: datetime) -> float | None:
    """Get the SII score closest to a given moment for a slug."""
    row = fetch_one(
        """
        SELECT overall_score FROM scores
        WHERE coingecko_id = %s AND computed_at <= %s
        ORDER BY computed_at DESC LIMIT 1
        """,
        (slug, when),
    )
    if row and row.get("overall_score") is not None:
        return float(row["overall_score"])
    row = fetch_one(
        """
        SELECT overall_score FROM score_history
        WHERE stablecoin = %s AND score_date <= %s::date
        ORDER BY score_date DESC LIMIT 1
        """,
        (slug, when),
    )
    if row and row.get("overall_score") is not None:
        return float(row["overall_score"])
    return None


def score_outcomes() -> int:
    """Fill outcome_30d/60d/90d for events that have aged past each window."""
    now = datetime.now(timezone.utc)
    rows = fetch_all(
        """
        SELECT id, entity_slug, event_timestamp, score_before, score_after,
               direction, outcome_30d, outcome_60d, outcome_90d
        FROM track_record_commitments
        WHERE outcome_90d IS NULL
          AND event_timestamp < NOW() - INTERVAL '30 days'
        ORDER BY event_timestamp ASC
        LIMIT 500
        """
    )
    updated = 0
    for r in rows or []:
        ts = r["event_timestamp"]
        if not ts:
            continue
        baseline = r.get("score_after") or r.get("score_before")
        if baseline is None:
            continue
        baseline = float(baseline)

        updates: dict[str, Any] = {}
        for horizon in (30, 60, 90):
            col = f"outcome_{horizon}d"
            if r.get(col) is not None:
                continue
            target = ts + timedelta(days=horizon)
            if target > now:
                continue
            after = _score_at(r["entity_slug"], target)
            if after is None:
                continue
            delta = after - baseline
            # Sign by direction: a "down" call that came true is positive outcome.
            direction = (r.get("direction") or "").lower()
            if direction == "down":
                signed = -delta
            elif direction == "up":
                signed = delta
            else:
                signed = abs(delta)
            updates[col] = signed
            updates[f"{col[:-1]}_at"] = target

        if not updates:
            continue
        sets = ", ".join(f"{k} = %s" for k in updates.keys())
        params = list(updates.values()) + [r["id"]]
        execute(f"UPDATE track_record_commitments SET {sets} WHERE id = %s", tuple(params))
        updated += 1
    return updated


def pending_commits(limit: int = 50) -> list[dict]:
    """Events that have been recorded but not anchored on-chain yet."""
    return fetch_all(
        """
        SELECT id, event_type, entity_slug, event_hash, event_timestamp,
               state_root_at_event, magnitude, direction, score_before, score_after
        FROM track_record_commitments
        WHERE on_chain_tx_hash IS NULL
        ORDER BY event_timestamp ASC
        LIMIT %s
        """,
        (limit,),
    )


def mark_committed(event_id: int, tx_hash: str, chain: str, block: int | None) -> None:
    execute(
        """
        UPDATE track_record_commitments
        SET on_chain_tx_hash = %s, on_chain_chain = %s,
            on_chain_block = %s, committed_at = NOW()
        WHERE id = %s
        """,
        (tx_hash, chain, block, event_id),
    )
