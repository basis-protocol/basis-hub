"""
Oracle entityId computation — canonical implementation.
========================================================
Single source of truth for the bytes32 entityId that the keeper
publishes to BasisSIIOracle.publishReportHash on Base + Arbitrum.

The byte spec is defined in docs/oracle_option_c_routing.md §11 Q2
(amended 2026-05-03). This module mirrors that spec exactly. The
TypeScript port lives in keeper/optionC_keys.ts; both implementations
must reproduce the 15 worked-example hexes in the spec doc and in
docs/oracle_option_c_golden_vectors.json — CI fails if either diverges.

Do NOT inline this logic at call sites. The three thin adapters in
app/track_record.py, app/disputes.py, and app/methodology_hashes.py
delegate here.
"""

from datetime import datetime, timezone
from typing import Union

from eth_hash.auto import keccak


# Domain prefixes — UTF-8 literal bytes, exact match required.
# Any change to these strings is a v2 domain prefix and a new entityId
# space. Never edit in place. See spec §11 Q2 encoding rules.
DOMAIN_TRACK_RECORD = b"basis:track_record:v1"
DOMAIN_DISPUTE      = b"basis:dispute:v1"
DOMAIN_METHODOLOGY  = b"basis:methodology:v1"


def _selector4(field_value: str) -> bytes:
    """bytes4(keccak256(utf8(field_value))) — Solidity function-selector idiom.

    Used for both trigger_kind (track-record) and transition_kind (dispute).
    Deterministic from the field value with no governance / registry.
    """
    return keccak(field_value.encode("utf-8"))[:4]


def _uint64_be(n: int) -> bytes:
    """8-byte big-endian uint64 encoding."""
    return int(n).to_bytes(8, "big")


def _to_unix_seconds(value: Union[datetime, str, int, float]) -> int:
    """Coerce a TIMESTAMPTZ / ISO-8601 / unix-seconds value to int seconds.

    Sub-second precision is dropped; collisions at 1-second granularity
    are by definition the same event (per spec §11 Q2 encoding rules).
    """
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value)
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


def track_record_entity_id(
    entity_slug: str,
    trigger_kind: str,
    triggered_at: Union[datetime, str, int, float],
) -> str:
    """entityId for a track-record event row.

    Preimage per spec §11 Q2:
        DOMAIN_TRACK_RECORD || bytes4(keccak(trigger_kind))
                            || utf8(entity_slug)
                            || uint64_be(triggered_at_unix)
    """
    preimage = (
        DOMAIN_TRACK_RECORD
        + _selector4(trigger_kind)
        + entity_slug.encode("utf-8")
        + _uint64_be(_to_unix_seconds(triggered_at))
    )
    return "0x" + keccak(preimage).hex()


def dispute_entity_id(
    dispute_id: str,
    transition_kind: str,
    transition_index: int,
) -> str:
    """entityId for a dispute_transitions row.

    Preimage per spec §11 Q2 (amended to include transition_index so
    the entityId matches the schema's UNIQUE(dispute_id, transition_index)
    natural key):
        DOMAIN_DISPUTE || keccak(utf8(f"dispute:{dispute_id}"))
                       || bytes4(keccak(transition_kind))
                       || uint64_be(transition_index)
    """
    dispute_id_bytes32 = keccak(f"dispute:{dispute_id}".encode("utf-8"))
    preimage = (
        DOMAIN_DISPUTE
        + dispute_id_bytes32
        + _selector4(transition_kind)
        + _uint64_be(transition_index)
    )
    return "0x" + keccak(preimage).hex()


def methodology_entity_id(methodology_id: str) -> str:
    """entityId for a methodology_hashes row.

    Preimage per spec §11 Q2:
        DOMAIN_METHODOLOGY || utf8(methodology_id)

    methodology_id is taken raw — no normalization, no whitespace trim,
    no case folding. The methodology_hashes.methodology_id column is
    canonical.
    """
    preimage = DOMAIN_METHODOLOGY + methodology_id.encode("utf-8")
    return "0x" + keccak(preimage).hex()
