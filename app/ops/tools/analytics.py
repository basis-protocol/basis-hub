"""
Analytics module — engagement effectiveness, pipeline velocity, response rates.
Queries ops tables to compute operational metrics.
"""
import logging
from datetime import datetime, timezone
from app.database import fetch_one, fetch_all

logger = logging.getLogger(__name__)


def compute_analytics() -> dict:
    """Compute all analytics in one call."""
    return {
        "engagement": _engagement_analytics(),
        "pipeline": _pipeline_velocity(),
        "content": _content_effectiveness(),
        "api_usage": _api_usage_trends(),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def _engagement_analytics() -> dict:
    """Which engagement types get responses? What's the response rate?"""
    # Total engagements by type
    by_type = fetch_all(
        """SELECT action_type, COUNT(*) as total,
                  COUNT(CASE WHEN response IS NOT NULL AND response != '' THEN 1 END) as with_response
           FROM ops_target_engagement_log
           GROUP BY action_type
           ORDER BY total DESC"""
    ) or []

    # Response rate by channel
    by_channel = fetch_all(
        """SELECT channel, COUNT(*) as total,
                  COUNT(CASE WHEN response IS NOT NULL AND response != '' THEN 1 END) as with_response
           FROM ops_target_engagement_log
           WHERE channel IS NOT NULL
           GROUP BY channel
           ORDER BY total DESC"""
    ) or []

    # Response rate by target tier
    by_tier = fetch_all(
        """SELECT t.tier, COUNT(*) as total,
                  COUNT(CASE WHEN el.response IS NOT NULL AND el.response != '' THEN 1 END) as with_response
           FROM ops_target_engagement_log el
           JOIN ops_targets t ON el.target_id = t.id
           GROUP BY t.tier
           ORDER BY t.tier"""
    ) or []

    # Total counts
    total = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_engagement_log") or {"cnt": 0}
    with_response = fetch_one(
        "SELECT COUNT(*) as cnt FROM ops_target_engagement_log WHERE response IS NOT NULL AND response != ''"
    ) or {"cnt": 0}

    overall_rate = round(with_response["cnt"] / total["cnt"] * 100, 1) if total["cnt"] > 0 else 0

    return {
        "total_engagements": total["cnt"],
        "total_responses": with_response["cnt"],
        "overall_response_rate": overall_rate,
        "by_action_type": [
            {**dict(r), "response_rate": round(r["with_response"] / r["total"] * 100, 1) if r["total"] > 0 else 0}
            for r in by_type
        ],
        "by_channel": [
            {**dict(r), "response_rate": round(r["with_response"] / r["total"] * 100, 1) if r["total"] > 0 else 0}
            for r in by_channel
        ],
        "by_tier": [
            {**dict(r), "response_rate": round(r["with_response"] / r["total"] * 100, 1) if r["total"] > 0 else 0}
            for r in by_tier
        ],
    }


def _pipeline_velocity() -> dict:
    """How fast are targets progressing through pipeline stages?"""
    # Current stage distribution
    stage_dist = fetch_all(
        """SELECT pipeline_stage, tier, COUNT(*) as cnt
           FROM ops_targets
           GROUP BY pipeline_stage, tier
           ORDER BY tier, pipeline_stage"""
    ) or []

    # Targets that have advanced beyond not_started
    active = fetch_one(
        "SELECT COUNT(*) as cnt FROM ops_targets WHERE pipeline_stage != 'not_started'"
    ) or {"cnt": 0}

    # Average time from creation to first engagement (for targets that have engagement)
    avg_first_engagement = fetch_one(
        """SELECT AVG(EXTRACT(EPOCH FROM (first_eng - t.created_at)) / 86400) as avg_days
           FROM ops_targets t
           JOIN (
               SELECT target_id, MIN(created_at) as first_eng
               FROM ops_target_engagement_log
               GROUP BY target_id
           ) e ON t.id = e.target_id"""
    )

    # Targets with overdue next_action
    overdue = fetch_all(
        """SELECT id, name, tier, next_action, next_action_due
           FROM ops_targets
           WHERE next_action_due IS NOT NULL AND next_action_due < NOW()
           ORDER BY next_action_due ASC"""
    ) or []

    # Most recently active targets
    recently_active = fetch_all(
        """SELECT id, name, tier, pipeline_stage, last_action_at
           FROM ops_targets
           WHERE last_action_at IS NOT NULL
           ORDER BY last_action_at DESC
           LIMIT 5"""
    ) or []

    return {
        "stage_distribution": [dict(r) for r in stage_dist],
        "active_targets": active["cnt"],
        "avg_days_to_first_engagement": round(avg_first_engagement["avg_days"], 1) if avg_first_engagement and avg_first_engagement.get("avg_days") else None,
        "overdue_actions": [dict(r) for r in overdue],
        "recently_active": [dict(r) for r in recently_active],
    }


def _content_effectiveness() -> dict:
    """How effective is scraped content analysis? What's the bridge hit rate?"""
    total_content = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content") or {"cnt": 0}
    analyzed = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content WHERE analyzed = TRUE") or {"cnt": 0}
    bridges = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content WHERE bridge_found = TRUE") or {"cnt": 0}
    decided = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content WHERE founder_decision IS NOT NULL") or {"cnt": 0}
    approved = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content WHERE founder_decision = 'approved'") or {"cnt": 0}
    posted = fetch_one("SELECT COUNT(*) as cnt FROM ops_target_content WHERE founder_decision = 'posted'") or {"cnt": 0}

    bridge_rate = round(bridges["cnt"] / analyzed["cnt"] * 100, 1) if analyzed["cnt"] > 0 else 0
    approval_rate = round(approved["cnt"] / decided["cnt"] * 100, 1) if decided["cnt"] > 0 else 0

    # Average relevance score
    avg_relevance = fetch_one(
        "SELECT AVG(relevance_score) as avg FROM ops_target_content WHERE relevance_score IS NOT NULL"
    )

    return {
        "total_content": total_content["cnt"],
        "analyzed": analyzed["cnt"],
        "bridges_found": bridges["cnt"],
        "bridge_rate": bridge_rate,
        "founder_decisions": decided["cnt"],
        "approved": approved["cnt"],
        "posted": posted["cnt"],
        "approval_rate": approval_rate,
        "avg_relevance_score": round(avg_relevance["avg"], 3) if avg_relevance and avg_relevance.get("avg") else None,
    }


def _api_usage_trends() -> dict:
    """API usage over recent periods."""
    periods = {
        "today": "1 day",
        "week": "7 days",
        "month": "30 days",
    }
    usage = {}
    for label, interval in periods.items():
        try:
            row = fetch_one(
                f"SELECT COUNT(*) as cnt FROM api_request_log WHERE timestamp > NOW() - INTERVAL '{interval}'"
            )
            usage[label] = row["cnt"] if row else 0
        except Exception:
            usage[label] = 0

    # Unique API keys active
    try:
        active_keys = fetch_one(
            "SELECT COUNT(DISTINCT api_key_id) as cnt FROM api_request_log WHERE timestamp > NOW() - INTERVAL '7 days' AND api_key_id IS NOT NULL"
        )
    except Exception:
        active_keys = None

    return {
        "requests": usage,
        "active_api_keys_7d": active_keys["cnt"] if active_keys else 0,
    }
