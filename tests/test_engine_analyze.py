"""
Component 2a: Analysis endpoint skeleton tests.

Style: HTTP integration tests against a live server (same pattern as
tests/test_engine_coverage.py). All admin-authenticated endpoints; tests
skip cleanly if ADMIN_KEY isn't available in the environment.

Run:
    ADMIN_KEY=<key> BASE_URL=https://basisprotocol.xyz \\
      pytest tests/test_engine_analyze.py -v

Rate-limit budget (admin tier, 120/min): well under. ~15 requests across
the eight tests including cleanup.

Test cleanup: each test appends any analysis IDs it creates to a shared
list. An autouse fixture runs after every test and DELETEs them all. If
DELETE fails (transient, already-gone, or linked-artifact 409), the test
logs and continues — cleanup best-effort; production operator can GC
stragglers via GET /api/engine/analyses?status=archived if needed.

Tests:
  1. test_analyze_drift_returns_202              — happy path
  2. test_analyze_pending_flips_to_draft         — async state machine
  3. test_analyze_missing_peer_set_returns_422   — Pydantic validation
  4. test_analyze_unknown_entity_returns_404     — coverage check
  5. test_analyze_duplicate_returns_409          — uniqueness constraint
  6. test_analyze_force_new_archives_previous    — revision chain
  7. test_list_analyses_filters_by_entity        — list endpoint
  8. test_get_analysis_unknown_id_returns_404    — GET 404
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Iterator

import pytest


# ═════════════════════════════════════════════════════════════════
# Fixtures
# ═════════════════════════════════════════════════════════════════

# Accept either ADMIN_KEY (server convention) or BASIS_ADMIN_KEY (S2a
# prompt variant). Tests skip if neither is present so CI without the
# secret doesn't break the build.
def _resolve_admin_key() -> str | None:
    return os.environ.get("ADMIN_KEY") or os.environ.get("BASIS_ADMIN_KEY")


@pytest.fixture(scope="session")
def admin_key() -> str:
    key = _resolve_admin_key()
    if not key:
        pytest.skip(
            "ADMIN_KEY not set — skipping admin-authenticated engine tests. "
            "Export ADMIN_KEY (or BASIS_ADMIN_KEY) to run these tests."
        )
    return key


class _AdminAPI:
    """Thin wrapper around requests.Session that injects the admin header."""

    def __init__(self, session, base_url: str, admin_key: str):
        self._session = session
        self._base = base_url
        self._headers = {"x-admin-key": admin_key}

    def post(self, path: str, body: dict[str, Any] | None = None):
        return self._session.post(
            f"{self._base}{path}",
            json=body or {},
            headers=self._headers,
            timeout=30,
        )

    def get(self, path: str, params: dict[str, Any] | None = None):
        return self._session.get(
            f"{self._base}{path}",
            headers=self._headers,
            params=params,
            timeout=30,
        )

    def delete(self, path: str):
        return self._session.delete(
            f"{self._base}{path}",
            headers=self._headers,
            timeout=30,
        )


@pytest.fixture(scope="session")
def admin_api(base_url, session, admin_key) -> _AdminAPI:
    return _AdminAPI(session, base_url, admin_key)


# Shared list of analysis IDs created during a single test. Reset per test.
_created_ids: list[str] = []


@pytest.fixture(autouse=True)
def cleanup_created_analyses(admin_api) -> Iterator[None]:
    """After each test, DELETE every analysis it created. Best-effort;
    failures are logged (via assertion message context) but don't fail
    the test since we're already past the assertions."""
    _created_ids.clear()
    yield
    for aid in list(_created_ids):
        try:
            admin_api.delete(f"/api/engine/analyses/{aid}")
        except Exception as exc:
            # Don't let cleanup crash the test session; log via stderr.
            print(f"cleanup: failed to delete {aid}: {exc}")
    _created_ids.clear()


def _track(analysis_id: str) -> str:
    """Record an analysis id for post-test cleanup and pass it through."""
    _created_ids.append(analysis_id)
    return analysis_id


# ═════════════════════════════════════════════════════════════════
# 1. Happy path — POST returns 202 with pending status
# ═════════════════════════════════════════════════════════════════

def test_analyze_drift_returns_202(admin_api):
    resp = admin_api.post(
        "/api/engine/analyze",
        {
            "entity": "drift",
            "event_date": "2026-04-01",
            "peer_set": ["jupiter-perpetual-exchange"],
        },
    )
    assert resp.status_code == 202, resp.text[:400]
    data = resp.json()

    assert "analysis_id" in data
    assert data["status"] == "pending"
    assert data["entity"] == "drift"
    assert data["poll_url"] == f"/api/engine/analyses/{data['analysis_id']}"

    # UUID format check
    uuid.UUID(data["analysis_id"])
    _track(data["analysis_id"])


# ═════════════════════════════════════════════════════════════════
# 2. Async state machine — pending flips to draft after ~2s
# ═════════════════════════════════════════════════════════════════

def test_analyze_pending_flips_to_draft(admin_api):
    resp = admin_api.post(
        "/api/engine/analyze",
        {
            "entity": "kelp-rseth",
            "event_date": "2026-04-18",
            "peer_set": [],
        },
    )
    assert resp.status_code == 202, resp.text[:400]
    aid = _track(resp.json()["analysis_id"])

    # Background task sleeps STUB_FINALIZE_DELAY_SECONDS (2s). Poll a bit
    # longer than that to account for scheduler jitter.
    time.sleep(3.5)

    get_resp = admin_api.get(f"/api/engine/analyses/{aid}")
    assert get_resp.status_code == 200, get_resp.text[:400]
    analysis = get_resp.json()

    assert analysis["status"] == "draft", (
        f"status should have flipped to draft after 3.5s, still: "
        f"{analysis['status']}"
    )
    # Stub interpretation is present and tagged correctly
    assert analysis["interpretation"]["model_id"] == "template:stub"
    assert analysis["interpretation"]["prompt_version"] == "stub-s2a"
    assert analysis["interpretation"]["confidence"] == "insufficient"
    # Signal is empty (S2b populates)
    assert analysis["signal"]["baseline"] == []
    assert analysis["signal"]["pre_event"] == []
    assert analysis["signal"]["event_window"] == []
    assert analysis["signal"]["post_event"] == []
    # Recommendation blocks all artifact types
    assert analysis["artifact_recommendation"]["recommended"] == "nothing"


# ═════════════════════════════════════════════════════════════════
# 3. Pydantic validation — missing peer_set → 422
# ═════════════════════════════════════════════════════════════════

def test_analyze_missing_peer_set_returns_422(admin_api):
    resp = admin_api.post(
        "/api/engine/analyze",
        {"entity": "drift", "event_date": "2026-04-01"},
    )
    assert resp.status_code == 422, resp.text[:400]
    body = resp.json()
    # FastAPI's 422 payload has a "detail" list of validation errors
    assert "detail" in body
    # Confirm peer_set is the missing field flagged
    missing_fields = {tuple(err["loc"]) for err in body["detail"]}
    assert ("body", "peer_set") in missing_fields, (
        f"expected body.peer_set to be flagged; got {missing_fields}"
    )


# ═════════════════════════════════════════════════════════════════
# 4. Coverage check — unknown entity → 404
# ═════════════════════════════════════════════════════════════════

def test_analyze_unknown_entity_returns_404(admin_api):
    resp = admin_api.post(
        "/api/engine/analyze",
        {
            "entity": "this-entity-does-not-exist-xyz",
            "peer_set": [],
        },
    )
    assert resp.status_code == 404, resp.text[:400]
    body = resp.json()
    assert "detail" in body
    assert "coverage" in body["detail"].lower()


# ═════════════════════════════════════════════════════════════════
# 5. Uniqueness — second analyze for same (entity, event_date) → 409
# ═════════════════════════════════════════════════════════════════

def test_analyze_duplicate_returns_409(admin_api):
    body = {
        "entity": "drift",
        "event_date": "2026-04-02",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    first = admin_api.post("/api/engine/analyze", body)
    assert first.status_code == 202, first.text[:400]
    aid_first = _track(first.json()["analysis_id"])

    second = admin_api.post("/api/engine/analyze", body)
    assert second.status_code == 409, second.text[:400]
    detail = second.json()["detail"]
    assert detail["error"] == "analysis_already_exists"
    assert detail["existing_analysis_id"] == aid_first


# ═════════════════════════════════════════════════════════════════
# 6. force_new=true archives the previous row and creates a new one
# ═════════════════════════════════════════════════════════════════

def test_analyze_force_new_archives_previous(admin_api):
    body = {
        "entity": "drift",
        "event_date": "2026-04-03",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    first = admin_api.post("/api/engine/analyze", body)
    assert first.status_code == 202, first.text[:400]
    aid_first = _track(first.json()["analysis_id"])

    body_force = dict(body, force_new=True)
    second = admin_api.post("/api/engine/analyze", body_force)
    assert second.status_code == 202, second.text[:400]
    aid_second = _track(second.json()["analysis_id"])
    assert aid_second != aid_first

    # Old row is archived with supersedes_reason set
    old_resp = admin_api.get(f"/api/engine/analyses/{aid_first}")
    assert old_resp.status_code == 200, old_resp.text[:400]
    old = old_resp.json()
    assert old["status"] == "archived"
    assert old["supersedes_reason"] is not None
    # Doubly-linked revision chain: old.superseded_by_id == new.id
    assert old["superseded_by_id"] == aid_second

    # New row points back to the old via previous_analysis_id
    new_resp = admin_api.get(f"/api/engine/analyses/{aid_second}")
    assert new_resp.status_code == 200, new_resp.text[:400]
    new = new_resp.json()
    assert new["previous_analysis_id"] == aid_first


# ═════════════════════════════════════════════════════════════════
# 6a. Regression guard — psycopg2 UUID adapter registered at import
#
# Observed in Railway logs after S2a deploy:
#   psycopg2.ProgrammingError: can't adapt type 'UUID'
#   app/engine/analysis_persistence.py:132 in _insert_analysis_sync
#
# Root cause: psycopg2 doesn't adapt Python uuid.UUID objects by default.
# The force_new=true path INSERTs with previous_analysis_id as a UUID and
# crashes without register_uuid() called at module import time. Fixed by
# adding psycopg2.extras.register_uuid() at the top of
# app/engine/analysis_persistence.py.
#
# This test explicitly exercises the previous_analysis_id path and asserts
# the second POST returns 202, not 500, so a future regression (e.g., a
# refactor that drops the register_uuid call) surfaces as a named test
# failure rather than a diagnostic-free 500.
# ═════════════════════════════════════════════════════════════════

def test_analyze_force_new_archives_previous_uuid_adapter(admin_api):
    """Regression: force_new path must not 500 due to UUID adapter
    registration being absent. See commentary above."""
    body = {
        "entity": "usdc",
        "event_date": "2026-04-05",
        "peer_set": [],
    }
    first = admin_api.post("/api/engine/analyze", body)
    assert first.status_code == 202, first.text[:400]
    _track(first.json()["analysis_id"])

    body_force = dict(body, force_new=True)
    second = admin_api.post("/api/engine/analyze", body_force)
    # If register_uuid() is missing from analysis_persistence.py, this
    # returns 500 with "can't adapt type 'UUID'" in the traceback.
    assert second.status_code == 202, (
        f"force_new POST returned {second.status_code} — suspected "
        f"psycopg2 UUID adapter regression in analysis_persistence.py. "
        f"Body: {second.text[:400]}"
    )
    _track(second.json()["analysis_id"])


# ═════════════════════════════════════════════════════════════════
# 7. List endpoint filters by entity
# ═════════════════════════════════════════════════════════════════

def test_list_analyses_filters_by_entity(admin_api):
    resp = admin_api.post(
        "/api/engine/analyze",
        {
            "entity": "layerzero",
            "event_date": "2026-04-04",
            "peer_set": [],
        },
    )
    assert resp.status_code == 202, resp.text[:400]
    _track(resp.json()["analysis_id"])

    list_resp = admin_api.get(
        "/api/engine/analyses", params={"entity": "layerzero", "limit": 50}
    )
    assert list_resp.status_code == 200, list_resp.text[:400]
    rows = list_resp.json()
    assert isinstance(rows, list)
    assert len(rows) >= 1
    # Every row should match the filter (including archived rows from prior
    # test runs — the list endpoint doesn't hide archived by default)
    for row in rows:
        assert row["entity"] == "layerzero"


# ═════════════════════════════════════════════════════════════════
# 8. GET with unknown id → 404
# ═════════════════════════════════════════════════════════════════

def test_get_analysis_unknown_id_returns_404(admin_api):
    random_id = uuid.uuid4()
    resp = admin_api.get(f"/api/engine/analyses/{random_id}")
    assert resp.status_code == 404, resp.text[:400]
    body = resp.json()
    assert "detail" in body
    assert str(random_id) in body["detail"]
