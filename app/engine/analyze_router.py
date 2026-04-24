"""
Component 2 router: /api/engine/analyze + /api/engine/analyses/*

Endpoints:
  POST   /api/engine/analyze            — start a new analysis (202)
  GET    /api/engine/analyses/{id}      — fetch full Analysis
  GET    /api/engine/analyses           — list AnalysisSummary
  DELETE /api/engine/analyses/{id}      — hard delete (test cleanup / operator)

Auth: all four routes are admin-only per Step 0 §5. The admin-key check
matches the existing `_check_admin_key` pattern from app/server.py,
app/ops/routes.py, and app/ops/entity_routes.py — env var ADMIN_KEY,
header x-admin-key or query param ?key=, HMAC compare. Inlined here to
follow the established per-module convention rather than introducing a
shared app/engine/auth.py abstraction ahead of need.

S2a behavior: real coverage lookup + stub interpretation. The LLM
integration arrives in S2c.
"""

from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.engine.analysis import build_stub_analysis, fetch_coverage
from app.engine.analysis_persistence import (
    archive_analysis,
    delete_analysis,
    find_active_analysis,
    get_analysis,
    insert_analysis,
    link_superseded_by,
    list_analyses,
)
from app.engine.background_tasks import spawn_finalize_task
from app.engine.schemas import (
    Analysis,
    AnalysisStatus,
    AnalysisSummary,
    AnalyzeRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────
# Admin-key check (mirrors app.server._check_admin_key)
# ─────────────────────────────────────────────────────────────────

def _check_admin_key(request: Request) -> None:
    admin_key = os.environ.get("ADMIN_KEY", "")
    provided = (
        request.query_params.get("key", "")
        or request.headers.get("x-admin-key", "")
    )
    if not admin_key or not provided or not hmac.compare_digest(provided, admin_key):
        raise HTTPException(status_code=401, detail="Unauthorized")


# ─────────────────────────────────────────────────────────────────
# 202 response shape (lean summary; full Analysis via poll_url)
# ─────────────────────────────────────────────────────────────────

class AnalyzeAccepted(BaseModel):
    analysis_id: UUID
    status: AnalysisStatus
    entity: str
    created_at: datetime
    poll_url: str


# ─────────────────────────────────────────────────────────────────
# POST /api/engine/analyze
# ─────────────────────────────────────────────────────────────────

@router.post("/api/engine/analyze", status_code=202)
async def analyze(request: Request, payload: AnalyzeRequest) -> JSONResponse:
    _check_admin_key(request)

    coverage = await fetch_coverage(payload.entity)
    if coverage is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Basis coverage found for entity '{payload.entity}'. "
                "Cannot analyze an uncovered entity."
            ),
        )

    # Normalize to the matched slug from coverage so the row's entity
    # matches canonical naming, not whatever the caller typed (e.g.,
    # 'rseth' → 'kelp-rseth').
    entity = coverage.identifier

    # Idempotency check: one active analysis per (entity, event_date).
    existing = await find_active_analysis(entity, payload.event_date)
    previous_analysis_id: Optional[UUID] = None
    supersedes_reason: Optional[str] = None

    if existing is not None:
        if not payload.force_new:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "analysis_already_exists",
                    "message": (
                        f"An active analysis already exists for entity "
                        f"'{entity}' and event_date {payload.event_date}. "
                        "Set force_new=true to archive it and create a "
                        "new one."
                    ),
                    "existing_analysis_id": str(existing.id),
                    "existing_status": existing.status,
                },
            )
        # force_new=true: archive the existing row before inserting the new one.
        await archive_analysis(
            existing.id, reason="operator requested new analysis"
        )
        previous_analysis_id = existing.id
        supersedes_reason = "operator requested new analysis via force_new"

    # Build the stub AnalysisCreate (real coverage + stub everything else)
    analysis_create = build_stub_analysis(
        entity=entity,
        peer_set=payload.peer_set,
        event_date=payload.event_date,
        context=payload.context,
        coverage=coverage,
        previous_analysis_id=previous_analysis_id,
        supersedes_reason=supersedes_reason,
    )

    # Persist with status=pending. Background task flips to draft after ~2s.
    new_id = await insert_analysis(analysis_create, status="pending")

    # Link the old row's superseded_by_id pointer to the new row (doubly-
    # linked revision chain per schemas.py). Only applies to force_new path.
    if previous_analysis_id is not None:
        await link_superseded_by(previous_analysis_id, new_id)

    # Optionally skip the async flip for dry-run / save=False semantics.
    # S2a interprets save=False as "still persist but return immediately
    # without the status transition" — the row stays pending until
    # manually updated. Deferring true dry-run (no persist at all) to S2c
    # when the ephemeral Analysis return shape is useful.
    if payload.save:
        spawn_finalize_task(new_id)

    created_at = datetime.now(timezone.utc)
    accepted = AnalyzeAccepted(
        analysis_id=new_id,
        status="pending",
        entity=entity,
        created_at=created_at,
        poll_url=f"/api/engine/analyses/{new_id}",
    )
    return JSONResponse(
        status_code=202,
        content=accepted.model_dump(mode="json"),
    )


# ─────────────────────────────────────────────────────────────────
# GET /api/engine/analyses/{id}
# ─────────────────────────────────────────────────────────────────

@router.get("/api/engine/analyses/{analysis_id}", response_model=Analysis)
async def get_one(request: Request, analysis_id: UUID) -> Analysis:
    _check_admin_key(request)
    analysis = await get_analysis(analysis_id)
    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis with id {analysis_id}",
        )
    return analysis


# ─────────────────────────────────────────────────────────────────
# GET /api/engine/analyses
# ─────────────────────────────────────────────────────────────────

@router.get("/api/engine/analyses", response_model=list[AnalysisSummary])
async def list_all(
    request: Request,
    entity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AnalysisSummary]:
    _check_admin_key(request)
    return await list_analyses(
        entity=entity, status=status, limit=limit, offset=offset
    )


# ─────────────────────────────────────────────────────────────────
# DELETE /api/engine/analyses/{id}
#
# Hard delete. Admin-only. Used for test cleanup and operator correction.
# Refuses if engine_artifacts rows reference the analysis (C3/S2c concern;
# defensive guard — S2a has no artifact path).
# ─────────────────────────────────────────────────────────────────

@router.delete("/api/engine/analyses/{analysis_id}")
async def delete_one(request: Request, analysis_id: UUID) -> JSONResponse:
    _check_admin_key(request)
    result = await delete_analysis(analysis_id)
    if result == "not_found":
        raise HTTPException(
            status_code=404,
            detail=f"No analysis with id {analysis_id}",
        )
    if result == "has_artifacts":
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete: analysis has linked engine_artifacts rows. "
                "Delete artifacts first."
            ),
        )
    return JSONResponse(
        status_code=200,
        content={"status": "deleted", "id": str(analysis_id)},
    )
