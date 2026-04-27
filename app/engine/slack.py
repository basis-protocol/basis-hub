"""
Component 5: Slack delivery.

Posts notifications about engine artifacts to a Slack incoming webhook so
the operator sees freshly rendered drafts without polling the DB. When
SLACK_ENGINE_WEBHOOK_URL is unset (local dev, CI, sandbox) the same
payload is dumped to stdout via logger.info — no HTTP call, no failure
mode that blocks the pipeline.

Single public entry: post_artifact_notification(artifact, analysis,
review_url) returns a dict describing what happened (delivery channel +
status code or "stdout"). Never raises; transport failures are caught,
logged, and reported via the return dict so the caller can decide
whether to record them on the artifact (we tag them onto warnings).

The webhook payload uses Slack Block Kit so the operator gets a
clickable Approve URL inline, not a wall of plain text. Composition
mirrors the operator-workflow examples in Step 0 doc §6.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import httpx

from app.engine.schemas import Analysis, ArtifactResponse

logger = logging.getLogger(__name__)


_WEBHOOK_ENV = "SLACK_ENGINE_WEBHOOK_URL"

# Slack's documented timeout for incoming webhook POSTs is 10s; we
# tighten to 5s because the operator pipeline already waits on the
# render call and we'd rather degrade to stdout than stall the request.
_SLACK_TIMEOUT_SECONDS = 5.0


def _build_slack_blocks(
    artifact: ArtifactResponse,
    analysis: Analysis,
    review_url: Optional[str],
) -> dict:
    headline = analysis.interpretation.headline if analysis.interpretation else ""
    confidence = (
        analysis.interpretation.confidence if analysis.interpretation else "insufficient"
    )
    event_label = (
        analysis.event_date.isoformat() if analysis.event_date else "baseline"
    )

    title = (
        f"Engine draft ready — {analysis.entity} ({event_label}) "
        f"→ {artifact.artifact_type}"
    )

    fields = [
        {"type": "mrkdwn", "text": f"*Entity:*\n{analysis.entity}"},
        {"type": "mrkdwn", "text": f"*Event date:*\n{event_label}"},
        {"type": "mrkdwn", "text": f"*Artifact type:*\n{artifact.artifact_type}"},
        {"type": "mrkdwn", "text": f"*Confidence:*\n{confidence}"},
    ]

    blocks: list[dict] = [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "section", "fields": fields},
    ]

    if headline:
        blocks.append(
            {"type": "section", "text": {"type": "mrkdwn", "text": f"_{headline}_"}}
        )

    if artifact.warnings:
        warnings_text = "\n".join(f"• {w}" for w in artifact.warnings)
        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Warnings:*\n{warnings_text}"},
            }
        )

    if review_url:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Review:* <{review_url}|Open artifact>\n"
                        f"`POST {review_url}/approve` to publish · "
                        f"`POST {review_url}/reject` to discard"
                    ),
                },
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"artifact_id `{artifact.id}` · "
                        f"analysis_id `{artifact.analysis_id}`"
                    ),
                }
            ],
        }
    )

    return {"text": title, "blocks": blocks}


def post_artifact_notification(
    artifact: ArtifactResponse,
    analysis: Analysis,
    review_url: Optional[str] = None,
) -> dict:
    """Post a notification for a freshly rendered artifact.

    Returns a result dict:
      {"channel": "webhook" | "stdout", "ok": bool, "detail": str}

    Never raises. HTTP failures are logged and returned with ok=False
    so callers can persist the failure into artifact.warnings.
    """
    payload = _build_slack_blocks(artifact, analysis, review_url)
    webhook_url = os.environ.get(_WEBHOOK_ENV, "").strip()

    if not webhook_url:
        logger.info(
            "slack.post_artifact_notification: %s unset — stdout fallback. "
            "payload=%s",
            _WEBHOOK_ENV,
            json.dumps(payload),
        )
        return {
            "channel": "stdout",
            "ok": True,
            "detail": f"{_WEBHOOK_ENV} unset; logged to stdout",
        }

    try:
        with httpx.Client(timeout=_SLACK_TIMEOUT_SECONDS) as client:
            resp = client.post(webhook_url, json=payload)
    except httpx.HTTPError as exc:
        logger.warning(
            "slack.post_artifact_notification: transport error artifact_id=%s: %s",
            artifact.id, exc,
        )
        return {
            "channel": "webhook",
            "ok": False,
            "detail": f"transport error: {type(exc).__name__}",
        }

    if resp.status_code >= 400:
        logger.warning(
            "slack.post_artifact_notification: webhook %d artifact_id=%s body=%s",
            resp.status_code, artifact.id, resp.text[:200],
        )
        return {
            "channel": "webhook",
            "ok": False,
            "detail": f"webhook returned {resp.status_code}",
        }

    logger.info(
        "slack.post_artifact_notification: posted artifact_id=%s status=%d",
        artifact.id, resp.status_code,
    )
    return {
        "channel": "webhook",
        "ok": True,
        "detail": f"webhook returned {resp.status_code}",
    }
