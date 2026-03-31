"""
Operations Hub API routes — all under /api/ops/*
Protected by X-Admin-Key (same pattern as existing admin endpoints).
"""
import os
import json
import logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional

from app.database import fetch_one, fetch_all, execute

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _check_admin_key(request: Request):
    admin_key = os.environ.get("ADMIN_KEY", "")
    provided = (
        request.query_params.get("key", "")
        or request.headers.get("x-admin-key", "")
    )
    if not admin_key or provided != admin_key:
        raise HTTPException(status_code=401, detail="Unauthorized")


# =============================================================================
# Migration — apply ops schema
# =============================================================================

@router.post("/migrate")
async def run_migration(request: Request):
    _check_admin_key(request)
    try:
        from app.database import run_migration
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "migrations", "031_ops_hub.sql"
        )
        run_migration(migration_path)
        return {"status": "ok", "migration": "031_ops_hub"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Seed
# =============================================================================

@router.post("/seed")
async def seed_data(request: Request):
    _check_admin_key(request)
    try:
        from app.ops.seed import seed_all
        counts = seed_all()
        return {"status": "ok", "inserted": counts}
    except Exception as e:
        logger.error(f"Seed failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Targets
# =============================================================================

@router.get("/targets")
async def list_targets(
    request: Request,
    tier: Optional[int] = None,
    track: Optional[str] = None,
    stage: Optional[str] = None,
):
    _check_admin_key(request)
    conditions = []
    params = []
    if tier is not None:
        conditions.append("tier = %s")
        params.append(tier)
    if track:
        conditions.append("track = %s")
        params.append(track)
    if stage:
        conditions.append("pipeline_stage = %s")
        params.append(stage)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = fetch_all(f"SELECT * FROM ops_targets{where} ORDER BY tier, name", params or None)
    return {"targets": rows}


@router.get("/targets/{target_id}")
async def get_target(request: Request, target_id: int):
    _check_admin_key(request)
    target = fetch_one("SELECT * FROM ops_targets WHERE id = %s", (target_id,))
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    contacts = fetch_all(
        "SELECT * FROM ops_target_contacts WHERE target_id = %s", (target_id,)
    )
    content = fetch_all(
        "SELECT * FROM ops_target_content WHERE target_id = %s ORDER BY scraped_at DESC LIMIT 20",
        (target_id,),
    )
    engagement = fetch_all(
        "SELECT * FROM ops_target_engagement_log WHERE target_id = %s ORDER BY created_at DESC LIMIT 20",
        (target_id,),
    )
    exposure = fetch_one(
        "SELECT * FROM ops_target_exposure_reports WHERE target_id = %s ORDER BY generated_at DESC LIMIT 1",
        (target_id,),
    )

    return {
        "target": target,
        "contacts": contacts,
        "recent_content": content,
        "engagement_log": engagement,
        "latest_exposure": exposure,
    }


@router.put("/targets/{target_id}/stage")
async def update_target_stage(request: Request, target_id: int):
    _check_admin_key(request)
    body = await request.json()
    new_stage = body.get("stage")
    if not new_stage:
        raise HTTPException(status_code=400, detail="stage required")

    valid_stages = [
        "not_started", "recognition", "familiarity", "direct",
        "evaluating", "trying", "binding", "archived",
    ]
    if new_stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {valid_stages}")

    execute(
        "UPDATE ops_targets SET pipeline_stage = %s, last_action_at = NOW(), updated_at = NOW() WHERE id = %s",
        (new_stage, target_id),
    )
    return {"status": "ok", "target_id": target_id, "new_stage": new_stage}


@router.post("/targets/{target_id}/engagement")
async def log_engagement(request: Request, target_id: int):
    _check_admin_key(request)
    body = await request.json()
    action_type = body.get("action_type")
    if not action_type:
        raise HTTPException(status_code=400, detail="action_type required")

    execute(
        """INSERT INTO ops_target_engagement_log (target_id, contact_id, action_type, content, channel, next_action)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            target_id,
            body.get("contact_id"),
            action_type,
            body.get("content"),
            body.get("channel"),
            body.get("next_action"),
        ),
    )
    # Update target last_action
    execute(
        "UPDATE ops_targets SET last_action_at = NOW(), updated_at = NOW() WHERE id = %s",
        (target_id,),
    )
    return {"status": "ok"}


@router.post("/targets/{target_id}/notes")
async def append_notes(request: Request, target_id: int):
    _check_admin_key(request)
    body = await request.json()
    note_text = body.get("text", "")
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    execute(
        "UPDATE ops_targets SET notes = COALESCE(notes, '') || %s, updated_at = NOW() WHERE id = %s",
        (f"\n[{timestamp}] {note_text}", target_id),
    )
    return {"status": "ok"}


# =============================================================================
# Action Queue
# =============================================================================

@router.get("/queue")
async def get_action_queue(request: Request):
    _check_admin_key(request)
    rows = fetch_all(
        """SELECT c.*, t.name as target_name, t.tier, t.pipeline_stage
           FROM ops_target_content c
           JOIN ops_targets t ON c.target_id = t.id
           WHERE c.bridge_found = TRUE AND c.founder_decision IS NULL
           ORDER BY c.relevance_score DESC NULLS LAST, c.scraped_at DESC""",
    )
    return {"queue": rows}


@router.post("/content/{content_id}/decide")
async def decide_content(request: Request, content_id: int):
    _check_admin_key(request)
    body = await request.json()
    decision = body.get("decision")
    if decision not in ("approved", "edited", "skipped", "posted"):
        raise HTTPException(status_code=400, detail="decision must be: approved, edited, skipped, posted")

    updates = {"founder_decision": decision}
    params = [decision]

    if decision == "edited":
        edited_text = body.get("edited_text", "")
        execute(
            "UPDATE ops_target_content SET founder_decision = %s, founder_edited_text = %s WHERE id = %s",
            (decision, edited_text, content_id),
        )
    elif decision == "posted":
        execute(
            "UPDATE ops_target_content SET founder_decision = %s, posted_at = NOW() WHERE id = %s",
            (decision, content_id),
        )
    else:
        execute(
            "UPDATE ops_target_content SET founder_decision = %s WHERE id = %s",
            (decision, content_id),
        )

    return {"status": "ok", "content_id": content_id, "decision": decision}


# =============================================================================
# Content Feed
# =============================================================================

@router.get("/content/feed")
async def content_feed(
    request: Request,
    target_id: Optional[int] = None,
    limit: int = Query(default=50, le=200),
):
    _check_admin_key(request)
    if target_id:
        rows = fetch_all(
            """SELECT c.*, t.name as target_name
               FROM ops_target_content c
               JOIN ops_targets t ON c.target_id = t.id
               WHERE c.target_id = %s
               ORDER BY c.scraped_at DESC LIMIT %s""",
            (target_id, limit),
        )
    else:
        rows = fetch_all(
            """SELECT c.*, t.name as target_name
               FROM ops_target_content c
               JOIN ops_targets t ON c.target_id = t.id
               ORDER BY c.scraped_at DESC LIMIT %s""",
            (limit,),
        )
    return {"feed": rows}


# =============================================================================
# Health
# =============================================================================

@router.get("/health")
async def get_health(request: Request):
    _check_admin_key(request)
    from app.ops.tools.health_checker import get_latest_health
    checks = get_latest_health()
    return {"health": checks}


@router.post("/health/check")
async def run_health_check(request: Request):
    _check_admin_key(request)
    # Force-reload health checker module to pick up code changes without server restart
    import importlib
    import app.ops.tools.health_checker as _hc_mod
    importlib.reload(_hc_mod)
    try:
        results = _hc_mod.run_all_checks()
        return {"status": "ok", "checks": results}
    except Exception as e:
        logger.error(f"Health check run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Investors
# =============================================================================

@router.get("/investors")
async def list_investors(
    request: Request,
    tier: Optional[int] = None,
    stage: Optional[str] = None,
):
    _check_admin_key(request)
    conditions = []
    params = []
    if tier is not None:
        conditions.append("tier = %s")
        params.append(tier)
    if stage:
        conditions.append("stage = %s")
        params.append(stage)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = fetch_all(f"SELECT * FROM ops_investors{where} ORDER BY tier, name", params or None)
    return {"investors": rows}


@router.put("/investors/{investor_id}/stage")
async def update_investor_stage(request: Request, investor_id: int):
    _check_admin_key(request)
    body = await request.json()
    new_stage = body.get("stage")
    if not new_stage:
        raise HTTPException(status_code=400, detail="stage required")

    valid_stages = [
        "not_started", "researching", "warm_intro_sent", "meeting_scheduled",
        "meeting_completed", "dd_in_progress", "term_sheet", "closed", "passed",
        "advisor_in_place",
    ]
    if new_stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {valid_stages}")

    execute(
        "UPDATE ops_investors SET stage = %s, last_action_at = NOW(), updated_at = NOW() WHERE id = %s",
        (new_stage, investor_id),
    )
    return {"status": "ok", "investor_id": investor_id, "new_stage": new_stage}


@router.post("/investors/{investor_id}/interaction")
async def log_investor_interaction(request: Request, investor_id: int):
    _check_admin_key(request)
    body = await request.json()
    action_type = body.get("action_type")
    if not action_type:
        raise HTTPException(status_code=400, detail="action_type required")

    execute(
        """INSERT INTO ops_investor_interactions (investor_id, action_type, content, response, next_step)
           VALUES (%s, %s, %s, %s, %s)""",
        (investor_id, action_type, body.get("content"), body.get("response"), body.get("next_step")),
    )
    execute(
        "UPDATE ops_investors SET last_action_at = NOW(), updated_at = NOW() WHERE id = %s",
        (investor_id,),
    )
    return {"status": "ok"}


@router.get("/fundraise/dashboard")
async def fundraise_dashboard(request: Request):
    _check_admin_key(request)
    investors = fetch_all("SELECT * FROM ops_investors ORDER BY tier, name")

    # Compute seed trigger milestones from live data
    milestones = _compute_milestones()

    return {
        "investors": investors,
        "milestones": milestones,
        "raise": {"target": "$4M seed", "valuation": "$25-40M pre", "timing": "Jun-Jul 2026"},
    }


def _compute_milestones():
    """Compute seed trigger milestones from live database state."""
    milestones = []

    # 1. Renderers live (check if we can query this)
    try:
        # This is a placeholder — renderer count would come from a registry
        milestones.append({
            "name": "8+ renderers live",
            "target": 8,
            "current": None,
            "met": False,
            "auto": True,
        })
    except Exception:
        pass

    # 2. API external requests/day
    try:
        row = fetch_one(
            """SELECT COUNT(*) as cnt FROM api_request_log
               WHERE created_at > NOW() - INTERVAL '24 hours'
               AND api_key_id IS NOT NULL"""
        )
        api_count = row["cnt"] if row else 0
        milestones.append({
            "name": "API >500 external requests/day",
            "target": 500,
            "current": api_count,
            "met": api_count > 500,
            "auto": True,
        })
    except Exception:
        milestones.append({"name": "API >500 external requests/day", "target": 500, "current": 0, "met": False, "auto": True})

    # 3. Protocol teams citing scores
    try:
        row = fetch_one(
            """SELECT COUNT(*) as cnt FROM ops_target_engagement_log
               WHERE action_type IN ('comment_posted', 'forum_posted')
               AND response IS NOT NULL"""
        )
        citations = row["cnt"] if row else 0
        milestones.append({
            "name": "Protocol teams citing scores",
            "target": 1,
            "current": citations,
            "met": citations > 0,
            "auto": False,
        })
    except Exception:
        milestones.append({"name": "Protocol teams citing scores", "target": 1, "current": 0, "met": False, "auto": False})

    # 4. Snap submitted for audit (manual)
    milestones.append({
        "name": "Snap submitted for audit",
        "target": 1,
        "current": 0,
        "met": False,
        "auto": False,
    })

    # 5. DAO pilot in conversation
    try:
        row = fetch_one(
            """SELECT COUNT(*) as cnt FROM ops_targets
               WHERE tier = 1 AND pipeline_stage IN ('evaluating', 'trying', 'binding')"""
        )
        pilots = row["cnt"] if row else 0
        milestones.append({
            "name": "DAO pilot in conversation",
            "target": 1,
            "current": pilots,
            "met": pilots > 0,
            "auto": True,
        })
    except Exception:
        milestones.append({"name": "DAO pilot in conversation", "target": 1, "current": 0, "met": False, "auto": True})

    met_count = sum(1 for m in milestones if m["met"])
    return {"milestones": milestones, "met": met_count, "total": len(milestones), "threshold": 3}


# =============================================================================
# Exposure Reports
# =============================================================================

@router.post("/exposure/generate")
async def generate_exposure_report(request: Request):
    _check_admin_key(request)
    body = await request.json()
    target_id = body.get("target_id")
    if not target_id:
        raise HTTPException(status_code=400, detail="target_id required")

    from app.ops.tools.exposure import generate_exposure
    result = generate_exposure(target_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Target not found")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/exposure/{target_id}/latest")
async def get_latest_exposure(request: Request, target_id: int):
    _check_admin_key(request)
    row = fetch_one(
        "SELECT * FROM ops_target_exposure_reports WHERE target_id = %s ORDER BY generated_at DESC LIMIT 1",
        (target_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="No exposure report found")
    return row


# =============================================================================
# Scrape + Analyze
# =============================================================================

@router.post("/scrape")
async def scrape_url(request: Request):
    _check_admin_key(request)
    body = await request.json()
    target_id = body.get("target_id")
    url = body.get("url")
    source_type = body.get("source_type", "blog")

    if not target_id or not url:
        raise HTTPException(status_code=400, detail="target_id and url required")

    from app.ops.tools.scraper import scrape_target
    content_id = await scrape_target(target_id, url, source_type)
    if content_id is None:
        raise HTTPException(status_code=500, detail="Scrape failed")

    # Auto-trigger analysis
    from app.ops.tools.analyzer import analyze_content
    analysis = await analyze_content(content_id)

    return {"content_id": content_id, "analysis": analysis}


@router.post("/analyze/{content_id}")
async def analyze_content_endpoint(request: Request, content_id: int):
    _check_admin_key(request)
    from app.ops.tools.analyzer import analyze_content
    result = await analyze_content(content_id)
    if result is None:
        raise HTTPException(status_code=500, detail="Analysis failed")
    return {"content_id": content_id, "analysis": result}


# =============================================================================
# Monitor Webhook (called by Parallel Monitor)
# =============================================================================

@router.post("/webhook/monitor")
async def monitor_webhook(request: Request):
    """
    Webhook endpoint called by Parallel Monitor when content changes.
    No admin key required — Parallel calls this directly.
    Triggers scrape + analyze pipeline.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = body.get("event_type", body.get("type", ""))
    monitor_id = body.get("monitor_id", "")
    url = body.get("url", body.get("data", {}).get("url", ""))

    logger.info(f"Monitor webhook received: type={event_type}, monitor={monitor_id}, url={url}")

    if not url:
        return {"status": "ok", "action": "no_url"}

    # Try to match URL to a target
    # For now, store it and analyze — target matching can be refined
    from app.ops.tools.scraper import scrape_target
    from app.ops.tools.analyzer import analyze_content

    # Find the most likely target based on URL patterns
    target = _match_url_to_target(url)
    target_id = target["id"] if target else None

    if target_id:
        content_id = await scrape_target(target_id, url, "blog")
        if content_id:
            await analyze_content(content_id)
            return {"status": "ok", "action": "scraped_and_analyzed", "content_id": content_id}

    return {"status": "ok", "action": "no_target_match"}


def _match_url_to_target(url: str):
    """Match a URL to a target based on known URL patterns."""
    url_lower = url.lower()
    patterns = {
        "kpk.io": "karpatkey",
        "karpatkey": "karpatkey",
        "morpho.org": "Morpho",
        "forum.morpho": "Morpho",
        "steakhouse": "Steakhouse Financial",
        "governance.aave": "Aave governance",
        "forum.cow": "CoW DAO",
        "lido.fi": "Lido Earn",
        "agentkit": "AgentKit / Coinbase",
        "coinbase": "AgentKit / Coinbase",
    }
    for pattern, target_name in patterns.items():
        if pattern in url_lower:
            return fetch_one("SELECT id, name FROM ops_targets WHERE name = %s", (target_name,))
    return None


# =============================================================================
# Monitor Setup
# =============================================================================

@router.post("/monitors/setup")
async def setup_monitors_endpoint(request: Request):
    _check_admin_key(request)
    body = await request.json()
    webhook_base_url = body.get("webhook_base_url", "")
    if not webhook_base_url:
        raise HTTPException(status_code=400, detail="webhook_base_url required")

    from app.ops.tools.scraper import setup_monitors
    monitors = await setup_monitors(webhook_base_url)
    return {"status": "ok", "monitors": monitors}


# =============================================================================
# Content Items
# =============================================================================

@router.get("/content/items")
async def list_content_items(
    request: Request,
    status: Optional[str] = None,
    type: Optional[str] = None,
):
    _check_admin_key(request)
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if type:
        conditions.append("type = %s")
        params.append(type)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = fetch_all(
        f"SELECT * FROM ops_content_items{where} ORDER BY scheduled_for ASC NULLS LAST, created_at DESC",
        params or None,
    )
    return {"items": rows}


@router.post("/content/items")
async def create_content_item(request: Request):
    _check_admin_key(request)
    body = await request.json()
    execute(
        """INSERT INTO ops_content_items (type, title, content, target_channel, related_target_id, status, scheduled_for)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            body.get("type"),
            body.get("title"),
            body.get("content"),
            body.get("target_channel"),
            body.get("related_target_id"),
            body.get("status", "draft"),
            body.get("scheduled_for"),
        ),
    )
    return {"status": "ok"}


def register_ops_routes(app):
    """Register the ops router with the main FastAPI app."""
    app.include_router(router)
    logger.info("Operations Hub routes registered")
