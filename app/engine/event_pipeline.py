"""
Component 4: Event-to-analysis pipeline orchestrator.

When a new engine_events row lands (from defillama_hacks polling, manual
submission, or watchlist threshold crossing), this module's process_event()
takes care of:

  1. Loading the event row by id.
  2. Calling the internal analysis trigger (app.engine.analysis_pipeline.
     trigger_analysis) which handles coverage check + dedup + skeleton
     INSERT + spawn_finalize_task.
  3. Writing the resulting analysis_id back onto the events row and
     advancing its status:

        no coverage     → status='no_coverage', analysis_id=NULL
        existing reused → status='analyzed',    analysis_id=existing.id
        new created     → status='analyzed',    analysis_id=new_id
        any error       → status='error',       analysis_id=NULL
                          (operator_response carries the exception type)

  4. Logging the outcome so Railway logs trace each event end-to-end.

All status updates are async-safe via asyncio.to_thread wrappers around
the sync psycopg2 helpers in app.database.

Idempotency: callers are encouraged to spawn process_event(event_id) via
asyncio.create_task and forget it — running process_event twice on the
same event_id is harmless (the second pass sees the analysis is already
linked and short-circuits).

C5 addition: post_analysis_render_default_artifact() lives here as the
auto-render-on-finalize hook. After background_tasks.finalize_analysis
flips a row from 'pending' to 'draft', it calls this function which
loads the analysis, renders the recommended artifact (skipping
'nothing', blocked, or duplicate cases), and posts a Slack
notification. Failures are caught and logged — finalize_analysis must
not be blocked by render or Slack issues.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from uuid import UUID

from app.database import fetch_one, get_cursor
from app.engine.analysis_persistence import get_analysis
from app.engine.analysis_pipeline import TriggerResult, trigger_analysis
from app.engine.artifact_persistence import find_active_artifact
from app.engine.render import KNOWN_ARTIFACT_TYPES, render_artifact
from app.engine.schemas import ArtifactResponse
from app.engine.slack import post_artifact_notification

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Event-row read + write
# ─────────────────────────────────────────────────────────────────

def _load_event_sync(event_id: UUID) -> Optional[dict]:
    return fetch_one(
        """
        SELECT id, source, event_type, entity, event_date, severity,
               raw_event_data, analysis_id, status, detected_at
        FROM engine_events
        WHERE id = %s
        """,
        (str(event_id),),
    )


async def load_event(event_id: UUID) -> Optional[dict]:
    return await asyncio.to_thread(_load_event_sync, event_id)


def _update_event_sync(
    event_id: UUID,
    *,
    status: str,
    analysis_id: Optional[UUID] = None,
    operator_response: Optional[str] = None,
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE engine_events
            SET status = %s,
                analysis_id = COALESCE(%s, analysis_id),
                operator_response = COALESCE(%s, operator_response)
            WHERE id = %s
            """,
            (status, analysis_id, operator_response, str(event_id)),
        )


async def update_event(
    event_id: UUID,
    *,
    status: str,
    analysis_id: Optional[UUID] = None,
    operator_response: Optional[str] = None,
) -> None:
    await asyncio.to_thread(
        _update_event_sync,
        event_id,
        status=status,
        analysis_id=analysis_id,
        operator_response=operator_response,
    )


# ─────────────────────────────────────────────────────────────────
# Public entry: process a detected event
# ─────────────────────────────────────────────────────────────────

# Translate trigger outcomes into engine_events.status values.
_OUTCOME_TO_STATUS: dict[str, str] = {
    "created": "analyzed",
    "existing": "analyzed",
    "no_coverage": "no_coverage",
    "error": "error",
}


async def process_event(event_id: UUID) -> dict:
    """Resolve coverage, trigger analysis, link the result onto the
    event row. Returns a small summary dict for logging.

    Safe to call repeatedly on the same event_id — idempotency is
    handled by analysis_pipeline.trigger_analysis (find_active_analysis
    returns the existing row) and by the engine_events status update
    being a simple overwrite.
    """
    event = await load_event(event_id)
    if event is None:
        logger.error("process_event: event_id=%s not found", event_id)
        return {"event_id": str(event_id), "outcome": "not_found"}

    if event["status"] in ("analyzed", "dismissed", "no_coverage"):
        logger.info(
            "process_event: event_id=%s already terminal status=%s — skipping",
            event_id, event["status"],
        )
        return {
            "event_id": str(event_id),
            "outcome": "already_processed",
            "status": event["status"],
            "analysis_id": str(event["analysis_id"]) if event["analysis_id"] else None,
        }

    entity = event["entity"]
    event_date = event["event_date"]
    source = event["source"]
    detected_at = event["detected_at"]

    context_note = (
        f"Auto-triggered by C4 from source={source} event detected at "
        f"{detected_at.isoformat() if detected_at else 'unknown time'}"
    )

    try:
        result: TriggerResult = await trigger_analysis(
            entity=entity,
            event_date=event_date,
            peer_set=[],  # auto-trigger; operator can re-run with peers via /analyze
            context=context_note,
            force_new=False,
        )
    except Exception as exc:
        logger.exception(
            "process_event: trigger_analysis failed for event_id=%s entity=%s",
            event_id, entity,
        )
        await update_event(
            event_id,
            status="error",
            operator_response=f"trigger_analysis raised: {type(exc).__name__}",
        )
        return {
            "event_id": str(event_id),
            "outcome": "error",
            "error": type(exc).__name__,
        }

    new_status = _OUTCOME_TO_STATUS.get(result.outcome, "error")
    await update_event(
        event_id,
        status=new_status,
        analysis_id=result.analysis_id,
        operator_response=result.detail,
    )

    logger.info(
        "process_event: event_id=%s entity=%s outcome=%s analysis_id=%s status=%s",
        event_id, entity, result.outcome,
        result.analysis_id, new_status,
    )
    return {
        "event_id": str(event_id),
        "entity": entity,
        "outcome": result.outcome,
        "analysis_id": str(result.analysis_id) if result.analysis_id else None,
        "status": new_status,
    }


# ─────────────────────────────────────────────────────────────────
# Auto-render hook (C5)
# ─────────────────────────────────────────────────────────────────

async def post_analysis_render_default_artifact(
    analysis_id: UUID,
    review_url_base: Optional[str] = None,
) -> Optional[ArtifactResponse]:
    """After finalize_analysis flips an analysis to 'draft', auto-render
    the recommended artifact and notify Slack.

    Returns the rendered artifact on success, the existing active
    artifact on duplicate, or None when the hook deliberately skips
    (recommendation is 'nothing', blocked, unknown type, or analysis
    missing). Never raises; finalize_analysis must not be blocked.
    """
    try:
        analysis = await get_analysis(analysis_id)
        if analysis is None:
            logger.warning(
                "post_analysis_render_default_artifact: analysis %s not found",
                analysis_id,
            )
            return None

        recommendation = analysis.artifact_recommendation
        recommended = recommendation.recommended

        if recommended == "nothing":
            logger.info(
                "post_analysis_render_default_artifact: analysis_id=%s "
                "recommendation=nothing — skipping auto-render",
                analysis_id,
            )
            return None

        if recommended in recommendation.blocked:
            logger.warning(
                "post_analysis_render_default_artifact: analysis_id=%s "
                "recommended=%s is also in blocked — skipping",
                analysis_id, recommended,
            )
            return None

        if recommended not in KNOWN_ARTIFACT_TYPES:
            logger.warning(
                "post_analysis_render_default_artifact: analysis_id=%s "
                "recommended type %s not in renderer registry — skipping",
                analysis_id, recommended,
            )
            return None

        existing = await find_active_artifact(analysis_id, recommended)
        if existing is not None:
            logger.info(
                "post_analysis_render_default_artifact: analysis_id=%s "
                "type=%s already has active artifact %s — skipping",
                analysis_id, recommended, existing.id,
            )
            return existing

        artifact = await render_artifact(analysis, recommended)

        review_url = (
            f"{review_url_base.rstrip('/')}/api/engine/artifacts/{artifact.id}"
            if review_url_base
            else f"/api/engine/artifacts/{artifact.id}"
        )
        notification = post_artifact_notification(artifact, analysis, review_url)
        logger.info(
            "post_analysis_render_default_artifact: analysis_id=%s "
            "artifact_id=%s notification=%s",
            analysis_id, artifact.id, notification,
        )
        return artifact

    except Exception as exc:
        logger.exception(
            "post_analysis_render_default_artifact: failed for analysis_id=%s: %s",
            analysis_id, exc,
        )
        return None
