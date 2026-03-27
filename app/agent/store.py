"""
Verification Agent — Store
============================
Writes assessment events to the canonical database.
Every event is persisted, even silent ones.
"""

import json
import logging

from app.database import execute, fetch_one

logger = logging.getLogger(__name__)


def store_assessment(assessment: dict) -> str | None:
    """
    Insert assessment event into canonical database.
    Returns the UUID of the created event, or None if skipped.

    The only condition that prevents storage is a duplicate
    content_hash within the same hour (idempotency guard).
    """
    content_hash = assessment.get("content_hash")

    # Idempotency: skip if same content_hash exists in the last hour
    if content_hash:
        existing = fetch_one("""
            SELECT id FROM assessment_events
            WHERE content_hash = %s
            AND created_at > NOW() - INTERVAL '1 hour'
        """, (content_hash,))
        if existing:
            logger.debug(f"Duplicate assessment skipped (hash: {content_hash[:16]}...)")
            return None

    holdings_json = json.dumps(assessment.get("holdings_snapshot", []))
    trigger_json = json.dumps(assessment.get("trigger_detail", {}))

    row = fetch_one("""
        INSERT INTO assessment_events (
            wallet_address, chain, trigger_type, trigger_detail,
            wallet_risk_score, wallet_risk_grade,
            wallet_risk_score_prev, concentration_hhi,
            concentration_hhi_prev, coverage_ratio,
            total_stablecoin_value, holdings_snapshot,
            severity, broadcast, content_hash, methodology_version
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s,
            %s, %s, %s, %s
        ) RETURNING id::text
    """, (
        assessment["wallet_address"],
        assessment.get("chain", "ethereum"),
        assessment["trigger_type"],
        trigger_json,
        assessment.get("wallet_risk_score"),
        assessment.get("wallet_risk_grade"),
        assessment.get("wallet_risk_score_prev"),
        assessment.get("concentration_hhi"),
        assessment.get("concentration_hhi_prev"),
        assessment.get("coverage_ratio"),
        assessment.get("total_stablecoin_value"),
        holdings_json,
        assessment.get("severity", "silent"),
        assessment.get("broadcast", False),
        content_hash,
        assessment.get("methodology_version", "wallet-v1.0.0"),
    ))

    event_id = row["id"] if row else None
    if event_id:
        logger.info(
            f"Assessment stored: {event_id} | "
            f"wallet={assessment['wallet_address'][:10]}... | "
            f"trigger={assessment['trigger_type']} | "
            f"severity={assessment.get('severity')}"
        )
    return event_id
