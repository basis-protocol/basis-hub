"""
Publisher — Pipeline
=====================
Subscribes to new assessment events and dispatches to renderers
based on severity and configuration.
"""

import logging

from app.agent.config import AGENT_CONFIG

logger = logging.getLogger(__name__)


async def publish(assessment: dict) -> dict:
    """
    Propagate assessment through the five-layer architecture.

    Layer 1 (Canonical):    Always. Already stored by agent.
    Layer 2 (Machine):      Always. Update page + API cache.
    Layer 3 (Amplification): Only if broadcast=True.
    Layer 4 (Contextual):   Manual/deferred. Not automated.
    Layer 5 (Institutional): Aggregated. Weekly/monthly.

    Returns a dict summarizing what was published.
    """
    config = AGENT_CONFIG
    result = {"layers": []}

    # Layer 1: Canonical — already stored by agent/store.py
    result["layers"].append("canonical")

    # Layer 2: Machine — update pages + API
    if config.get("pages_enabled"):
        try:
            from app.publisher.page_renderer import (
                update_wallet_page, update_asset_pages, create_assessment_page
            )
            await update_wallet_page(assessment)
            await update_asset_pages(assessment)
            if assessment.get("broadcast"):
                await create_assessment_page(assessment)
            result["layers"].append("machine")
        except Exception as e:
            logger.error(f"Page rendering failed: {e}")

    # Layer 3: Amplification — only on broadcast
    if assessment.get("broadcast"):
        severity = assessment.get("severity", "silent")

        if config.get("social_enabled") and severity in ("alert", "critical"):
            try:
                from app.publisher.social_renderer import post_alert
                await post_alert(assessment)
                result["layers"].append("social")
            except Exception as e:
                logger.warning(f"Social posting skipped: {e}")

        if config.get("onchain_enabled") and severity == "critical":
            try:
                from app.publisher.onchain_renderer import post_attestation
                await post_attestation(assessment)
                result["layers"].append("onchain")
            except Exception as e:
                logger.warning(f"On-chain posting skipped: {e}")

    logger.info(
        f"Published assessment {assessment.get('id', '?')}: "
        f"layers={result['layers']}"
    )
    return result
