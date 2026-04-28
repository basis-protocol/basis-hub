"""
Component 5 router: /api/engine/artifacts/{id}/approve and /reject.

Both endpoints are admin-only. The shape mirrors the inline
_check_admin_key pattern used in analyze_router/render_router/budget_router
(no shared dependency module).

POST /api/engine/artifacts/{id}/approve
    body: {"reviewer": str?, "notes": str?}
    success 200: {"artifact": ArtifactResponse, "commit": {...},
                  "detail": "approved + committed"}
    409 if state != 'draft' (already discarded, etc.) — except
        already-published which returns 200 as a no-op.
    502 if git commit failed (artifact stays draft so operator can retry).

POST /api/engine/artifacts/{id}/reject
    body: {"reviewer": str?, "notes": str?}
    success 200: {"artifact": ArtifactResponse, "detail": "..."}

Both endpoints catch the local ArtifactStateError into 409s with a
machine-readable error code so the operator UI can disambiguate
"already done" from "wrong state".
"""

from __future__ import annotations

import hmac
import logging
import os
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.engine.approval import (
    ApprovalResult,
    ArtifactStateError,
    approve_artifact,
    reject_artifact,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_admin_key(request: Request) -> None:
    admin_key = os.environ.get("ADMIN_KEY", "")
    provided = (
        request.query_params.get("key", "")
        or request.headers.get("x-admin-key", "")
    )
    if not admin_key or not provided or not hmac.compare_digest(provided, admin_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


class ReviewRequest(BaseModel):
    reviewer: Optional[str] = Field(
        default=None,
        description="Free-text identifier for the operator approving/rejecting "
        "(email, github handle, etc.). Stored verbatim in artifact warnings.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional review notes; stored alongside reviewer in warnings.",
    )


def _result_to_response(result: ApprovalResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "artifact": result.artifact.model_dump(mode="json"),
        "detail": result.detail,
    }
    if result.commit is not None:
        payload["commit"] = {
            "status": result.commit.status,
            "commit_url": result.commit.commit_url,
            "detail": result.commit.detail,
            "test_mode": result.commit.test_mode,
        }
    if result.notification is not None:
        payload["notification"] = result.notification
    return payload


@router.post("/api/engine/artifacts/{artifact_id}/approve")
async def approve(
    artifact_id: UUID,
    request: Request,
    payload: Optional[ReviewRequest] = None,
) -> dict[str, Any]:
    _check_admin_key(request)
    payload = payload or ReviewRequest()

    try:
        result = await approve_artifact(
            artifact_id,
            reviewer=payload.reviewer,
            notes=payload.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ArtifactStateError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_state_for_approve", "message": str(exc)},
        )

    if result.commit is not None and result.commit.status == "failed":
        # Keep the row in draft so the operator can retry once the
        # underlying issue (PAT, network, repo policy) is resolved.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "commit_failed",
                "message": result.commit.detail or "git commit failed",
                "artifact_id": str(artifact_id),
            },
        )

    return _result_to_response(result)


@router.post("/api/engine/artifacts/{artifact_id}/reject")
async def reject(
    artifact_id: UUID,
    request: Request,
    payload: Optional[ReviewRequest] = None,
) -> dict[str, Any]:
    _check_admin_key(request)
    payload = payload or ReviewRequest()

    try:
        result = await reject_artifact(
            artifact_id,
            reviewer=payload.reviewer,
            notes=payload.notes,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ArtifactStateError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "invalid_state_for_reject", "message": str(exc)},
        )

    return _result_to_response(result)
