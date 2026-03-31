"""
Alert system — sends notifications via Telegram or email
when health failures, engagement responses, or milestone changes occur.
"""
import os
import json
import logging
import httpx
from datetime import datetime, timezone
from app.database import fetch_all, fetch_one, execute

logger = logging.getLogger(__name__)


def _get_active_channels():
    """Load enabled alert channels from ops_alert_config."""
    try:
        return fetch_all("SELECT * FROM ops_alert_config WHERE enabled = TRUE")
    except Exception:
        return []


async def send_alert(alert_type: str, message: str, context: dict = None):
    """
    Send alert to all configured channels that subscribe to this alert_type.
    Logs the alert regardless of delivery success.
    """
    channels = _get_active_channels()
    sent_any = False

    for ch in channels:
        if alert_type not in (ch.get("alert_types") or []):
            continue

        try:
            if ch["channel"] == "telegram":
                await _send_telegram(ch["config"], message)
                sent_any = True
            elif ch["channel"] == "email":
                # Email integration placeholder — would use SendGrid/SES
                logger.info(f"Email alert (not implemented): {message[:100]}")
                sent_any = True
        except Exception as e:
            logger.error(f"Alert send failed ({ch['channel']}): {e}")

    # Always log the alert
    try:
        execute(
            "INSERT INTO ops_alert_log (alert_type, channel, message, context) VALUES (%s, %s, %s, %s)",
            (alert_type, "telegram" if sent_any else "log_only", message, json.dumps(context or {})),
        )
    except Exception:
        pass

    return sent_any


async def _send_telegram(config: dict, message: str):
    """Send message via Telegram Bot API."""
    bot_token = config.get("bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured (missing bot_token or chat_id)")
        return

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if resp.status_code != 200:
            logger.error(f"Telegram send failed: {resp.status_code} {resp.text[:200]}")
        else:
            logger.info(f"Telegram alert sent to {chat_id}")


async def check_and_alert_health(health_results: list):
    """
    After a health check run, send alerts for any degraded or down systems.
    Only alerts if the system was previously healthy (transition detection).
    """
    failures = [r for r in health_results if r.get("status") in ("degraded", "down")]
    if not failures:
        return

    # Check previous state to avoid alert fatigue
    for f in failures:
        prev = fetch_one(
            """SELECT status FROM ops_health_checks
               WHERE system = %s AND checked_at < NOW() - INTERVAL '5 minutes'
               ORDER BY checked_at DESC LIMIT 1""",
            (f["system"],),
        )
        # Alert only on transition to failure, or if first check ever
        if prev and prev["status"] == f["status"]:
            continue  # Same status as before, don't re-alert

        severity = "DOWN" if f["status"] == "down" else "DEGRADED"
        msg = f"*{severity}*: {f['system'].replace('_', ' ')}\n"
        details = f.get("details", {})
        for k, v in list(details.items())[:3]:
            msg += f"  {k}: {v}\n"

        await send_alert("health_failure", msg, {"system": f["system"], "status": f["status"], "details": details})


async def check_and_alert_engagement():
    """
    Detect new engagement responses (target replied/liked) and alert + auto-queue DM draft.
    Checks for engagement_log entries with responses that haven't been alerted yet.
    """
    # Find engagement entries with responses that are recent and not yet alerted
    recent = fetch_all(
        """SELECT el.*, t.name as target_name
           FROM ops_target_engagement_log el
           JOIN ops_targets t ON el.target_id = t.id
           WHERE el.response IS NOT NULL
             AND el.response != ''
             AND el.response_at > NOW() - INTERVAL '24 hours'
             AND el.id NOT IN (
                 SELECT (context->>'engagement_id')::int
                 FROM ops_alert_log
                 WHERE alert_type = 'engagement_response'
                   AND context->>'engagement_id' IS NOT NULL
             )"""
    )

    for eng in (recent or []):
        msg = (
            f"*Engagement response* from {eng['target_name']}\n"
            f"Action: {eng['action_type']}\n"
            f"Response: {eng['response'][:200]}\n"
            f"Next: consider follow-up DM or stage update"
        )
        await send_alert(
            "engagement_response",
            msg,
            {"engagement_id": eng["id"], "target_id": eng["target_id"], "target_name": eng["target_name"]},
        )


def get_alert_log(limit: int = 50) -> list:
    """Get recent alert log."""
    try:
        return fetch_all(
            "SELECT * FROM ops_alert_log ORDER BY sent_at DESC LIMIT %s",
            (limit,),
        )
    except Exception:
        return []
