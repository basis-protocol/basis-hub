"""
Component 5: Approval orchestration.

Public entries:
  approve_artifact(artifact_id, reviewer, notes) → ApprovalResult
  reject_artifact(artifact_id, reviewer, notes)  → ApprovalResult

The auto-render-on-finalize hook lives in event_pipeline.py
(post_analysis_render_default_artifact); approve/reject is the
operator-driven mirror that lives here.

State machine for engine_artifacts.status (canonical literals from
schemas.ArtifactStatus):

    draft ──approve──► published
       └──reject──► discarded

Idempotency rules:
  - approving an artifact already in 'published' is a no-op success
    (returns the existing published_url).
  - approving anything in 'discarded' is a 409.
  - rejecting an artifact already in 'discarded' is a no-op success.
  - rejecting anything in 'published' is a 409 (you can't unpublish via
    this surface; that requires a fresh render + re-approve cycle).

The ArtifactResponse model has no review_notes field and the
engine_artifacts table has no review_notes column. Per the C5 prompt
("no schema changes"), we stash the reviewer + free-text notes inside
the existing warnings JSONB array as tagged strings, e.g.:

    "[review:approved by alex@basis.foundation] looks good, ship it"
    "[review:rejected by ops@basis.foundation] coverage too sparse"

Renderers can filter these out by prefix when displaying warnings.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

import psycopg2.extras

from app.database import fetch_one, get_cursor
from app.engine.artifact_persistence import get_artifact
from app.engine.git_commit import CommitResult, commit_artifact
from app.engine.schemas import ArtifactResponse, ArtifactStatus

logger = logging.getLogger(__name__)

# Idempotent. Mirrors precedent in artifact_persistence.py and
# analysis_persistence.py — module import registers the UUID adapter.
psycopg2.extras.register_uuid()


# Tag prefixes — lets renderers strip review chatter from operator
# warnings if they want a clean display.
_APPROVE_TAG_PREFIX = "[review:approved"
_REJECT_TAG_PREFIX = "[review:rejected"


@dataclass
class ApprovalResult:
    artifact: ArtifactResponse
    commit: Optional[CommitResult] = None
    notification: Optional[dict] = None
    detail: Optional[str] = None


class ArtifactStateError(ValueError):
    """Raised when the requested transition isn't legal for the
    artifact's current status. Endpoints map to 409."""


# ─────────────────────────────────────────────────────────────────
# Status updates — local sync helpers (no edits to artifact_persistence)
# ─────────────────────────────────────────────────────────────────

def _update_artifact_sync(
    artifact_id: UUID,
    *,
    new_status: ArtifactStatus,
    published_url: Optional[str],
    warnings: list[str],
) -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE engine_artifacts
            SET status = %s,
                published_url = COALESCE(%s, published_url),
                warnings = %s
            WHERE id = %s
            """,
            (
                new_status,
                published_url,
                psycopg2.extras.Json(list(warnings)),
                str(artifact_id),
            ),
        )


async def _persist_status(
    artifact_id: UUID,
    *,
    new_status: ArtifactStatus,
    published_url: Optional[str],
    warnings: list[str],
) -> None:
    await asyncio.to_thread(
        _update_artifact_sync,
        artifact_id,
        new_status=new_status,
        published_url=published_url,
        warnings=warnings,
    )


def _format_review_note(action: str, reviewer: Optional[str], notes: Optional[str]) -> str:
    who = reviewer or "unknown"
    text = (notes or "").strip()
    body = f" {text}" if text else ""
    return f"[review:{action} by {who}]{body}"


# ─────────────────────────────────────────────────────────────────
# Approve
# ─────────────────────────────────────────────────────────────────

async def approve_artifact(
    artifact_id: UUID,
    reviewer: Optional[str] = None,
    notes: Optional[str] = None,
) -> ApprovalResult:
    """Commit the artifact to the repo and flip its status to 'published'.

    Idempotent on already-published rows (returns the existing
    published_url). Raises ArtifactStateError when the artifact is in a
    state that can't be approved.
    """
    artifact = await get_artifact(artifact_id)
    if artifact is None:
        raise LookupError(f"No artifact with id {artifact_id}")

    if artifact.status == "published":
        logger.info(
            "approve_artifact: artifact_id=%s already published — no-op",
            artifact_id,
        )
        return ApprovalResult(
            artifact=artifact,
            detail="already published; no-op",
        )

    if artifact.status == "discarded":
        raise ArtifactStateError(
            f"artifact {artifact_id} is discarded; cannot approve"
        )

    if artifact.status != "draft":
        raise ArtifactStateError(
            f"artifact {artifact_id} has status {artifact.status!r}; "
            "only 'draft' can be approved"
        )

    commit_result = await commit_artifact(artifact)
    if commit_result.status == "failed":
        logger.warning(
            "approve_artifact: commit failed artifact_id=%s detail=%s",
            artifact_id, commit_result.detail,
        )
        return ApprovalResult(
            artifact=artifact,
            commit=commit_result,
            detail=f"commit failed: {commit_result.detail}",
        )

    new_warnings = list(artifact.warnings)
    new_warnings.append(_format_review_note("approved", reviewer, notes))

    published_url = commit_result.commit_url
    await _persist_status(
        artifact_id,
        new_status="published",
        published_url=published_url,
        warnings=new_warnings,
    )

    refreshed = await get_artifact(artifact_id)
    assert refreshed is not None  # we just updated it
    logger.info(
        "approve_artifact: artifact_id=%s -> published url=%s reviewer=%s",
        artifact_id, published_url, reviewer,
    )
    return ApprovalResult(
        artifact=refreshed,
        commit=commit_result,
        detail="approved + committed",
    )


# ─────────────────────────────────────────────────────────────────
# Reject
# ─────────────────────────────────────────────────────────────────

async def reject_artifact(
    artifact_id: UUID,
    reviewer: Optional[str] = None,
    notes: Optional[str] = None,
) -> ApprovalResult:
    """Mark the artifact 'discarded' and stash the reviewer + reason in
    warnings. No git operations; rejected drafts never leave the DB.
    """
    artifact = await get_artifact(artifact_id)
    if artifact is None:
        raise LookupError(f"No artifact with id {artifact_id}")

    if artifact.status == "discarded":
        logger.info(
            "reject_artifact: artifact_id=%s already discarded — no-op",
            artifact_id,
        )
        return ApprovalResult(artifact=artifact, detail="already discarded; no-op")

    if artifact.status == "published":
        raise ArtifactStateError(
            f"artifact {artifact_id} is already published; reject is "
            "not a rollback path. Render a fresh artifact and approve "
            "the replacement instead."
        )

    if artifact.status != "draft":
        raise ArtifactStateError(
            f"artifact {artifact_id} has status {artifact.status!r}; "
            "only 'draft' can be rejected"
        )

    new_warnings = list(artifact.warnings)
    new_warnings.append(_format_review_note("rejected", reviewer, notes))
    await _persist_status(
        artifact_id,
        new_status="discarded",
        published_url=None,  # no overwrite
        warnings=new_warnings,
    )

    refreshed = await get_artifact(artifact_id)
    assert refreshed is not None
    logger.info(
        "reject_artifact: artifact_id=%s -> discarded reviewer=%s",
        artifact_id, reviewer,
    )
    return ApprovalResult(artifact=refreshed, detail="rejected + discarded")


# ─────────────────────────────────────────────────────────────────
# Read helper used by tests / inspection
# ─────────────────────────────────────────────────────────────────

def fetch_artifact_status_sync(artifact_id: UUID) -> Optional[str]:
    row = fetch_one(
        "SELECT status FROM engine_artifacts WHERE id = %s",
        (str(artifact_id),),
    )
    return row["status"] if row else None
