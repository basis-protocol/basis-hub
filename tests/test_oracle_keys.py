"""
Tests for app/oracle_keys.py — canonical entityId computation.

Loads the 15 golden vectors from docs/oracle_option_c_golden_vectors.json
(single source of truth shared with keeper/optionC_keys.test.ts) and
asserts byte-exact match per vector.

Also covers:
  - Adapter delegation: the three compute_on_chain_entity_id thin
    adapters (track_record / disputes / methodology_hashes) produce
    the same hex as direct calls to app.oracle_keys.
  - triggered_at coercion: datetime / ISO string / int all yield
    the same entityId.
  - Domain prefix collision separation: identical "natural keys"
    across types do NOT collide.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.oracle_keys import (
    DOMAIN_DISPUTE,
    DOMAIN_METHODOLOGY,
    DOMAIN_TRACK_RECORD,
    dispute_entity_id,
    methodology_entity_id,
    track_record_entity_id,
    _selector4,
)


# =============================================================================
# Golden vectors — loaded from spec-aligned JSON
# =============================================================================

GOLDEN_PATH = Path(__file__).parent.parent / "docs" / "oracle_option_c_golden_vectors.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text())


# =============================================================================
# Track-record vectors (5)
# =============================================================================

@pytest.mark.parametrize("vec", GOLDEN["track_record"], ids=lambda v: v["label"])
def test_track_record_golden(vec):
    got = track_record_entity_id(
        vec["entity_slug"], vec["trigger_kind"], vec["triggered_at_unix"]
    )
    assert got == vec["expected_entity_id"], (
        f"Track-record entityId mismatch for {vec['label']!r}\n"
        f"  expected: {vec['expected_entity_id']}\n"
        f"  got:      {got}"
    )


# =============================================================================
# Dispute vectors (5)
# =============================================================================

@pytest.mark.parametrize("vec", GOLDEN["dispute"], ids=lambda v: v["label"])
def test_dispute_golden(vec):
    got = dispute_entity_id(
        vec["dispute_id"], vec["transition_kind"], vec["transition_index"]
    )
    assert got == vec["expected_entity_id"], (
        f"Dispute entityId mismatch for {vec['label']!r}\n"
        f"  expected: {vec['expected_entity_id']}\n"
        f"  got:      {got}"
    )


# =============================================================================
# Methodology vectors (5)
# =============================================================================

@pytest.mark.parametrize("vec", GOLDEN["methodology"], ids=lambda v: v["label"])
def test_methodology_golden(vec):
    got = methodology_entity_id(vec["methodology_id"])
    assert got == vec["expected_entity_id"], (
        f"Methodology entityId mismatch for {vec['label']!r}\n"
        f"  expected: {vec['expected_entity_id']}\n"
        f"  got:      {got}"
    )


# =============================================================================
# Selector helper (8 cross-reference values)
# =============================================================================

@pytest.mark.parametrize("name,expected_hex", list(GOLDEN["selectors"].items()))
def test_selector4_cross_reference(name, expected_hex):
    if name.startswith("_"):
        pytest.skip("comment field")
    got = "0x" + _selector4(name).hex()
    assert got == expected_hex


# =============================================================================
# Adapter delegation — the three thin adapters
# =============================================================================

def test_track_record_adapter_delegates():
    """app.track_record.compute_on_chain_entity_id calls oracle_keys."""
    from app.track_record import compute_on_chain_entity_id
    vec = GOLDEN["track_record"][0]
    got = compute_on_chain_entity_id({
        "entity_slug": vec["entity_slug"],
        "trigger_kind": vec["trigger_kind"],
        "triggered_at": vec["triggered_at_unix"],
    })
    assert got == vec["expected_entity_id"]


def test_dispute_adapter_delegates():
    from app.disputes import compute_on_chain_entity_id
    vec = GOLDEN["dispute"][0]
    got = compute_on_chain_entity_id({
        "dispute_id": vec["dispute_id"],
        "transition_kind": vec["transition_kind"],
        "transition_index": vec["transition_index"],
    })
    assert got == vec["expected_entity_id"]


def test_methodology_adapter_delegates():
    from app.methodology_hashes import compute_on_chain_entity_id
    vec = GOLDEN["methodology"][0]
    got = compute_on_chain_entity_id({"methodology_id": vec["methodology_id"]})
    assert got == vec["expected_entity_id"]


# =============================================================================
# triggered_at coercion — datetime / ISO string / int yield same hex
# =============================================================================

def test_track_record_triggered_at_coercion():
    """SVB/USDC vector via three input shapes — all must produce the same entityId."""
    vec = GOLDEN["track_record"][0]  # SVB/USDC depeg

    via_int = track_record_entity_id(
        vec["entity_slug"], vec["trigger_kind"], vec["triggered_at_unix"]
    )
    via_iso = track_record_entity_id(
        vec["entity_slug"], vec["trigger_kind"], vec["triggered_at_iso"]
    )
    via_dt = track_record_entity_id(
        vec["entity_slug"],
        vec["trigger_kind"],
        datetime.fromtimestamp(vec["triggered_at_unix"], tz=timezone.utc),
    )
    assert via_int == via_iso == via_dt == vec["expected_entity_id"]


# =============================================================================
# Domain-prefix collision separation
# =============================================================================

def test_domain_prefix_constants_are_distinct():
    assert DOMAIN_TRACK_RECORD != DOMAIN_DISPUTE
    assert DOMAIN_DISPUTE != DOMAIN_METHODOLOGY
    assert DOMAIN_TRACK_RECORD != DOMAIN_METHODOLOGY


def test_domain_prefix_separates_collisions():
    """Two commits with the 'same' natural key across types must not collide."""
    # Same string fed to all three — entityIds must differ purely on domain.
    s = "lens_registry_v1"
    meth = methodology_entity_id(s)
    # Track-record with entity_slug=s, arbitrary trigger / time
    track = track_record_entity_id(s, "manual", 0)
    # Dispute with dispute_id=s, arbitrary kind / index
    disp = dispute_entity_id(s, "submission", 0)
    assert len({meth, track, disp}) == 3, (
        "Domain prefixes failed to separate collisions: "
        f"meth={meth} track={track} disp={disp}"
    )


# =============================================================================
# Sanity: the spec doc tables and the JSON file agree
# =============================================================================

def test_golden_json_has_15_vectors():
    assert len(GOLDEN["track_record"]) == 5
    assert len(GOLDEN["dispute"]) == 5
    assert len(GOLDEN["methodology"]) == 5


def test_golden_json_lens_registry_anchor_matches_spec_q3():
    """The lens_registry_v1 entityId is the anchor for §11 Q3 commit 1.
    If this hex changes, runbook §5.1 mainnet sequence breaks.
    """
    lens_vec = next(
        v for v in GOLDEN["methodology"] if v["methodology_id"] == "lens_registry_v1"
    )
    assert lens_vec["expected_entity_id"] == (
        "0x54ab550521b1ed07db401b7931e85b9123033df6fbf195c91fe35b8e47474cf2"
    )
