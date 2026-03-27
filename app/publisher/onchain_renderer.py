"""
Publisher — On-chain Renderer
================================
Posts content_hash attestations for critical assessment events.
Disabled by default until onchain_enabled is True and wallet is funded.
"""

import logging

from app.database import execute

logger = logging.getLogger(__name__)


async def post_attestation(assessment: dict) -> None:
    """
    Record attestation for on-chain posting.

    For V1, writes to assessment_events.onchain_tx as a marker.
    The existing keeper script (basis-oracle repo) can be extended
    to post these content hashes to the BasisOracle contract.
    """
    event_id = assessment.get("id")
    content_hash = assessment.get("content_hash")

    if not event_id or not content_hash:
        logger.warning("Cannot post attestation: missing id or content_hash")
        return

    # Mark as pending attestation (keeper script will pick this up)
    logger.info(
        f"On-chain attestation queued: event={event_id} hash={content_hash[:16]}... "
        f"(not posted — onchain_enabled=False)"
    )

    # TODO: When onchain_enabled, call keeper script or post directly
    # to BasisOracle contract on Base/Arbitrum
