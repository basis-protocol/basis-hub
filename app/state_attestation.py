"""
Universal State Attestation
=============================
Hash any batch of novel state at capture time.
Every domain of state that cannot be reconstructed retroactively
gets hashed when it is persisted.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from app.database import execute, fetch_one, fetch_one_async, fetch_all_async, execute_async
from app.scoring import FORMULA_VERSION

logger = logging.getLogger(__name__)


def _serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def compute_batch_hash(records: list[dict]) -> str:
    """Compute SHA-256 of canonical sorted JSON representation of records."""
    canonical = json.dumps(
        sorted(records, key=lambda r: json.dumps(r, sort_keys=True, default=_serialize)),
        sort_keys=True,
        separators=(",", ":"),
        default=_serialize,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def store_attestation(
    domain: str,
    batch_hash: str,
    record_count: int,
    entity_id: str = None,
    methodology_version: str = None,
) -> None:
    """Store a state attestation record."""
    await execute_async(
        """
        INSERT INTO state_attestations
            (domain, entity_id, batch_hash, record_count, methodology_version, cycle_timestamp)
        VALUES (%s, %s, %s, %s, %s, NOW())
        """,
        (domain, entity_id, batch_hash, record_count, methodology_version or FORMULA_VERSION),
    )


def attest_state(domain: str, records: list[dict], entity_id: str = None) -> str:
    """Compute hash and store attestation in one call. Returns the hash."""
    if not records:
        return ""
    batch_hash = compute_batch_hash(records)
    store_attestation(domain, batch_hash, len(records), entity_id)
    logger.info(f"State attested: domain={domain} entity={entity_id} records={len(records)} hash={batch_hash[:16]}...")
    return batch_hash


async def get_latest_attestation(domain: str, entity_id: str = None) -> dict | None:
    """Get the most recent attestation for a domain/entity."""
    if entity_id:
        return await fetch_one_async(
            """
            SELECT domain, entity_id, batch_hash, record_count, methodology_version, cycle_timestamp
            FROM state_attestations
            WHERE domain = %s AND entity_id = %s
            ORDER BY cycle_timestamp DESC LIMIT 1
            """,
            (domain, entity_id),
        )
    return await fetch_one_async(
        """
        SELECT domain, entity_id, batch_hash, record_count, methodology_version, cycle_timestamp
        FROM state_attestations
        WHERE domain = %s AND entity_id IS NULL
        ORDER BY cycle_timestamp DESC LIMIT 1
        """,
        (domain,),
    )
