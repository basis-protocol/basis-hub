"""
Component 5: Operator workflow tests — Slack delivery, git commit
TEST_MODE bypass, and the approve/reject endpoints.

8 unit tests against pure helpers (Slack payload composition, stdout
fallback, git_commit TEST_MODE bypass, PAT redaction, path traversal
defense, approval state machine guards) — fast, no HTTP, no DB writes.

4 integration tests against POST /api/engine/artifacts/{id}/approve
and /reject. Use BASIS_ENGINE_TEST_MODE=1 so no real PAT is needed and
no real push happens; the endpoint returns the fake commit URL and the
DB row flips to 'published'.

Run:
    ADMIN_KEY=<key> BASE_URL=https://basisprotocol.xyz \\
      DATABASE_URL=<prod-url> BASIS_ENGINE_TEST_MODE=1 \\
      pytest tests/test_engine_workflow.py -v

Cleanup mirrors test_engine_renderers.py: artifacts → analyses ordering
because of the FK on engine_artifacts.analysis_id.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.engine.approval import (
    ArtifactStateError,
    _format_review_note,
    approve_artifact,
    reject_artifact,
)
from app.engine.git_commit import (
    CommitResult,
    _is_test_mode,
    _redact,
    _validate_relative_path,
    commit_artifact,
)
from app.engine.schemas import (
    ArtifactRecommendation,
    ArtifactResponse,
    CoverageResponse,
    EntityCoverage,
    Interpretation,
)
from app.engine.slack import (
    _WEBHOOK_ENV,
    _build_slack_blocks,
    post_artifact_notification,
)


# ═════════════════════════════════════════════════════════════════
# Test fixture (entity, event_date) keys
# ═════════════════════════════════════════════════════════════════

TEST_FIXTURE_KEYS: list[tuple[str, date]] = [
    ("drift", date(2026, 6, 1)),  # test_approve_endpoint_flips_to_published
    ("drift", date(2026, 6, 2)),  # test_reject_endpoint_flips_to_discarded
    ("drift", date(2026, 6, 3)),  # test_approve_endpoint_idempotent_on_published
    ("drift", date(2026, 6, 4)),  # test_reject_endpoint_409_on_published
]


# ═════════════════════════════════════════════════════════════════
# DB cleanup — artifacts before analyses
# ═════════════════════════════════════════════════════════════════

def _db_delete_for_test_keys() -> int:
    conn_string = os.environ.get("DATABASE_URL")
    if not conn_string:
        return -1
    try:
        import psycopg2
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM engine_analyses
                    WHERE (entity, event_date) IN %s
                    """,
                    (tuple(TEST_FIXTURE_KEYS),),
                )
                ids = [r[0] for r in cur.fetchall()]
                if not ids:
                    return 0
                cur.execute(
                    "DELETE FROM engine_artifacts WHERE analysis_id = ANY(%s::uuid[])",
                    ([str(i) for i in ids],),
                )
                arts_deleted = cur.rowcount
                cur.execute(
                    "DELETE FROM engine_analyses WHERE id = ANY(%s::uuid[])",
                    ([str(i) for i in ids],),
                )
                analyses_deleted = cur.rowcount
            conn.commit()
        return arts_deleted + analyses_deleted
    except Exception as exc:
        print(f"cleanup: workflow sweep failed: {exc}", file=sys.stderr)
        return -1


def _db_delete_for_analysis_ids(ids: list[str]) -> bool:
    if not ids:
        return True
    conn_string = os.environ.get("DATABASE_URL")
    if not conn_string:
        return False
    try:
        import psycopg2
        with psycopg2.connect(conn_string) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM engine_artifacts WHERE analysis_id = ANY(%s::uuid[])",
                    ([str(i) for i in ids],),
                )
                cur.execute(
                    "DELETE FROM engine_analyses WHERE id = ANY(%s::uuid[])",
                    ([str(i) for i in ids],),
                )
            conn.commit()
        return True
    except Exception as exc:
        print(f"cleanup: per-test delete failed: {exc}", file=sys.stderr)
        return False


# ═════════════════════════════════════════════════════════════════
# Fixtures (admin auth + cleanup)
# ═════════════════════════════════════════════════════════════════

def _resolve_admin_key() -> Optional[str]:
    return os.environ.get("ADMIN_KEY") or os.environ.get("BASIS_ADMIN_KEY")


@pytest.fixture(scope="session")
def admin_key() -> str:
    key = _resolve_admin_key()
    if not key:
        pytest.skip(
            "ADMIN_KEY not set — skipping admin-authenticated integration tests."
        )
    return key


class _AdminAPI:
    def __init__(self, session, base_url: str, admin_key: str):
        self._session = session
        self._base = base_url
        self._headers = {"x-admin-key": admin_key}

    def post(self, path: str, body: dict[str, Any] | None = None):
        return self._session.post(
            f"{self._base}{path}",
            json=body or {},
            headers=self._headers,
            timeout=90,
        )

    def get(self, path: str):
        return self._session.get(
            f"{self._base}{path}", headers=self._headers, timeout=30,
        )


@pytest.fixture(scope="session")
def admin_api(base_url, session, admin_key) -> _AdminAPI:
    return _AdminAPI(session, base_url, admin_key)


@pytest.fixture(scope="session", autouse=True)
def session_workflow_cleanup():
    deleted = _db_delete_for_test_keys()
    if deleted > 0:
        print(
            f"\n[workflow-tests] session-start sweep: deleted {deleted} "
            "stale row(s) (artifacts + analyses)",
            file=sys.stderr,
        )
    yield
    _db_delete_for_test_keys()


_created_ids: list[str] = []


@pytest.fixture(autouse=True)
def cleanup_created_analyses() -> Iterator[None]:
    _created_ids.clear()
    yield
    if _created_ids:
        _db_delete_for_analysis_ids(list(_created_ids))
        _created_ids.clear()


def _track(analysis_id: str) -> str:
    _created_ids.append(analysis_id)
    return analysis_id


def _wait_for_draft(admin_api, analysis_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        resp = admin_api.get(f"/api/engine/analyses/{analysis_id}")
        if resp.status_code == 200:
            body = resp.json()
            if body.get("status") != "pending":
                return body
        time.sleep(0.7)
    return body


def _render_default_artifact(admin_api, analysis_id: str) -> dict:
    """Return an active draft artifact for the analysis. C5's auto-render
    hook fires inside finalize_analysis, so by the time the analysis
    flips to 'draft' there may already be an artifact rendered. Check
    GET /artifacts first; if none exists, render the recommended type
    explicitly (falling back to internal_memo when the recommendation
    is 'nothing' or blocked)."""
    list_resp = admin_api.get(f"/api/engine/analyses/{analysis_id}/artifacts")
    if list_resp.status_code == 200:
        existing = [
            a for a in list_resp.json()
            if a.get("status") == "draft"
        ]
        if existing:
            # Return the freshest (DB orders DESC by rendered_at).
            return existing[0]

    full = admin_api.get(f"/api/engine/analyses/{analysis_id}").json()
    recommended = full["artifact_recommendation"]["recommended"]
    candidate = recommended if recommended != "nothing" else "internal_memo"
    resp = admin_api.post(
        "/api/engine/render",
        {"analysis_id": analysis_id, "artifact_type": candidate},
    )
    if resp.status_code == 422 and candidate != "internal_memo":
        resp = admin_api.post(
            "/api/engine/render",
            {"analysis_id": analysis_id, "artifact_type": "internal_memo"},
        )
    assert resp.status_code == 202, resp.text[:400]
    return resp.json()


# ═════════════════════════════════════════════════════════════════
# Helper builders
# ═════════════════════════════════════════════════════════════════

def _make_artifact(
    *,
    artifact_id: Optional[UUID] = None,
    analysis_id: Optional[UUID] = None,
    suggested_path: Optional[str] = "content/test.md",
    status: str = "draft",
    warnings: Optional[list[str]] = None,
) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact_id or uuid4(),
        analysis_id=analysis_id or uuid4(),
        artifact_type="internal_memo",
        rendered_at=datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc),
        content_markdown="# Test\n\nBody.",
        suggested_path=suggested_path,
        suggested_url=None,
        status=status,  # type: ignore[arg-type]
        published_url=None,
        warnings=warnings or [],
    )


def _make_minimal_analysis_for_slack() -> Any:
    """Smallest possible Analysis-like object to test Slack block building.
    Slack only reads .entity, .event_date, .interpretation. Use a MagicMock
    so we don't have to construct a full Analysis (peer_set, signal, etc)."""
    interp = Interpretation(
        event_summary="Summary.",
        what_this_does_not_claim="Nothing.",
        headline="Drift PSI dropped 12pts vs Jupiter.",
        confidence="medium",
        confidence_reasoning="Partial coverage.",
        prompt_version="v1",
        input_hash="sha256:test",
        model_id="claude-sonnet-4-6",
        generated_at=datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc),
        from_cache=False,
    )
    mock = MagicMock()
    mock.entity = "drift"
    mock.event_date = date(2026, 4, 27)
    mock.interpretation = interp
    return mock


# ═════════════════════════════════════════════════════════════════
# 1. Unit: slack stdout fallback when env unset
# ═════════════════════════════════════════════════════════════════

def test_slack_stdout_fallback_when_webhook_unset(monkeypatch):
    """No SLACK_ENGINE_WEBHOOK_URL env → no HTTP call, returns
    channel='stdout' with ok=True."""
    monkeypatch.delenv(_WEBHOOK_ENV, raising=False)
    artifact = _make_artifact()
    analysis = _make_minimal_analysis_for_slack()

    with patch("app.engine.slack.httpx.Client") as client_cls:
        result = post_artifact_notification(
            artifact, analysis, review_url="https://example/api/engine/artifacts/x"
        )

    assert client_cls.call_count == 0, (
        "stdout fallback must not invoke httpx"
    )
    assert result["channel"] == "stdout"
    assert result["ok"] is True


# ═════════════════════════════════════════════════════════════════
# 2. Unit: slack block kit composition includes title + entity + url
# ═════════════════════════════════════════════════════════════════

def test_slack_blocks_include_required_fields():
    artifact = _make_artifact(warnings=["sparse coverage"])
    analysis = _make_minimal_analysis_for_slack()
    payload = _build_slack_blocks(
        artifact, analysis, review_url="https://example/api/engine/artifacts/x"
    )

    # Top-level
    assert "text" in payload
    assert "blocks" in payload
    assert "drift" in payload["text"]
    assert "internal_memo" in payload["text"]

    # Stringify all block content for substring assertions
    blob = str(payload["blocks"])
    assert "drift" in blob
    assert "2026-04-27" in blob
    assert "internal_memo" in blob
    assert "https://example/api/engine/artifacts/x" in blob
    assert "approve" in blob
    assert "reject" in blob
    # Warnings included
    assert "sparse coverage" in blob


# ═════════════════════════════════════════════════════════════════
# 3. Unit: slack webhook transport error returns ok=False
# ═════════════════════════════════════════════════════════════════

def test_slack_webhook_transport_error_returns_ok_false(monkeypatch):
    """A transport error (timeout, connection refused) is caught; the
    function returns ok=False with a descriptive detail rather than
    raising."""
    monkeypatch.setenv(_WEBHOOK_ENV, "https://hooks.slack.com/services/FAKE")
    import httpx

    class _FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def post(self, *_a, **_kw):
            raise httpx.ConnectError("simulated DNS failure")

    artifact = _make_artifact()
    analysis = _make_minimal_analysis_for_slack()
    with patch("app.engine.slack.httpx.Client", _FakeClient):
        result = post_artifact_notification(artifact, analysis, review_url="x")

    assert result["channel"] == "webhook"
    assert result["ok"] is False
    assert "transport error" in result["detail"]


# ═════════════════════════════════════════════════════════════════
# 4. Unit: git_commit TEST_MODE bypass returns fake URL, no shell-out
# ═════════════════════════════════════════════════════════════════

def test_git_commit_test_mode_bypass(monkeypatch):
    monkeypatch.setenv("BASIS_ENGINE_TEST_MODE", "1")
    artifact = _make_artifact(suggested_path="content/case-study/test.md")

    with patch("app.engine.git_commit.subprocess.run") as run_mock:
        import asyncio
        result = asyncio.run(commit_artifact(artifact))

    assert run_mock.call_count == 0, (
        "TEST_MODE must skip every subprocess.run call"
    )
    assert result.status == "committed"
    assert result.test_mode is True
    assert result.commit_url is not None
    assert "test-mode" in result.commit_url


# ═════════════════════════════════════════════════════════════════
# 5. Unit: PAT redaction scrubs secret from output
# ═════════════════════════════════════════════════════════════════

def test_git_commit_pat_redaction():
    pat = "ghp_supersecretvalue1234567890"
    text = (
        f"fatal: could not push to https://x-access-token:{pat}@github.com/"
        f"repo: bad creds"
    )
    redacted = _redact(text, pat)
    assert pat not in redacted
    assert "***REDACTED***" in redacted

    # Defensive: empty/None secret leaves the text unchanged
    assert _redact("hello", "") == "hello"
    assert _redact("hello", None) == "hello"
    # Defensive: empty text passes through
    assert _redact("", pat) == ""


# ═════════════════════════════════════════════════════════════════
# 6. Unit: path traversal rejected by _validate_relative_path
# ═════════════════════════════════════════════════════════════════

def test_git_commit_rejects_path_traversal(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()

    # Sane path inside workspace
    target = _validate_relative_path("content/foo.md", workspace)
    assert target.is_relative_to(workspace.resolve())

    # Escape via ..
    with pytest.raises(ValueError):
        _validate_relative_path("../etc/passwd", workspace)

    # Absolute path
    with pytest.raises(ValueError):
        _validate_relative_path("/etc/shadow", workspace)

    # Empty
    with pytest.raises(ValueError):
        _validate_relative_path("", workspace)


# ═════════════════════════════════════════════════════════════════
# 7. Unit: approve refuses non-draft state with ArtifactStateError
# ═════════════════════════════════════════════════════════════════

def test_approve_refuses_non_draft_state(monkeypatch):
    """When the artifact in the DB is in 'discarded', approve_artifact
    raises ArtifactStateError. 'published' is special-cased as a no-op
    and is verified separately by an integration test."""
    discarded_artifact = _make_artifact(status="discarded")

    async def fake_get(_id):
        return discarded_artifact

    monkeypatch.setattr("app.engine.approval.get_artifact", fake_get)

    import asyncio
    with pytest.raises(ArtifactStateError):
        asyncio.run(approve_artifact(discarded_artifact.id, reviewer="test"))


# ═════════════════════════════════════════════════════════════════
# 8. Unit: reject refuses 'published' state — no rollback path
# ═════════════════════════════════════════════════════════════════

def test_reject_refuses_published_state(monkeypatch):
    published = _make_artifact(status="published")

    async def fake_get(_id):
        return published

    monkeypatch.setattr("app.engine.approval.get_artifact", fake_get)

    import asyncio
    with pytest.raises(ArtifactStateError):
        asyncio.run(reject_artifact(published.id, reviewer="test"))

    # Sanity: review-note formatter shape is what the DB will receive
    note = _format_review_note("approved", "alex@basis.foundation", "ship it")
    assert note.startswith("[review:approved by alex@basis.foundation]")
    assert "ship it" in note


# ═════════════════════════════════════════════════════════════════
# 9. Integration: POST /approve flips status to 'published'
# ═════════════════════════════════════════════════════════════════

def test_approve_endpoint_flips_to_published(admin_api):
    """End-to-end: create analysis → wait for draft → render artifact →
    approve. With BASIS_ENGINE_TEST_MODE=1 set the commit returns a fake
    URL and the artifact status becomes 'published'."""
    if os.environ.get("BASIS_ENGINE_TEST_MODE", "").lower() not in ("1", "true", "yes"):
        pytest.skip(
            "BASIS_ENGINE_TEST_MODE must be set to '1' for approval "
            "integration tests so no real PAT/push is required."
        )

    body = {
        "entity": "drift",
        "event_date": "2026-06-01",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    resp = admin_api.post("/api/engine/analyze", body)
    assert resp.status_code == 202, resp.text[:400]
    aid = _track(resp.json()["analysis_id"])

    full = _wait_for_draft(admin_api, aid)
    assert full.get("status") == "draft"

    artifact = _render_default_artifact(admin_api, aid)
    artifact_id = artifact["id"]
    assert artifact["status"] == "draft"

    approve_resp = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/approve",
        {"reviewer": "test@basis.foundation", "notes": "C5 integration test"},
    )
    assert approve_resp.status_code == 200, approve_resp.text[:400]
    body_resp = approve_resp.json()
    assert body_resp["artifact"]["status"] == "published"
    assert body_resp["commit"]["test_mode"] is True
    assert "test-mode" in body_resp["commit"]["commit_url"]
    assert body_resp["artifact"]["published_url"] == body_resp["commit"]["commit_url"]


# ═════════════════════════════════════════════════════════════════
# 10. Integration: POST /reject flips status to 'discarded'
# ═════════════════════════════════════════════════════════════════

def test_reject_endpoint_flips_to_discarded(admin_api):
    body = {
        "entity": "drift",
        "event_date": "2026-06-02",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    resp = admin_api.post("/api/engine/analyze", body)
    assert resp.status_code == 202, resp.text[:400]
    aid = _track(resp.json()["analysis_id"])

    full = _wait_for_draft(admin_api, aid)
    assert full.get("status") == "draft"

    artifact = _render_default_artifact(admin_api, aid)
    artifact_id = artifact["id"]

    reject_resp = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/reject",
        {"reviewer": "test@basis.foundation", "notes": "low confidence; revisit"},
    )
    assert reject_resp.status_code == 200, reject_resp.text[:400]
    body_resp = reject_resp.json()
    assert body_resp["artifact"]["status"] == "discarded"
    # No commit happens on reject
    assert "commit" not in body_resp or body_resp["commit"] is None
    # Review note stashed in warnings
    warnings = body_resp["artifact"]["warnings"]
    assert any(
        "[review:rejected" in w and "low confidence" in w
        for w in warnings
    ), f"expected review-note warning; got {warnings}"


# ═════════════════════════════════════════════════════════════════
# 11. Integration: re-approving a published artifact is a no-op
# ═════════════════════════════════════════════════════════════════

def test_approve_endpoint_idempotent_on_published(admin_api):
    if os.environ.get("BASIS_ENGINE_TEST_MODE", "").lower() not in ("1", "true", "yes"):
        pytest.skip("BASIS_ENGINE_TEST_MODE required.")

    body = {
        "entity": "drift",
        "event_date": "2026-06-03",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    resp = admin_api.post("/api/engine/analyze", body)
    assert resp.status_code == 202, resp.text[:400]
    aid = _track(resp.json()["analysis_id"])

    full = _wait_for_draft(admin_api, aid)
    assert full.get("status") == "draft"

    artifact = _render_default_artifact(admin_api, aid)
    artifact_id = artifact["id"]

    first = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/approve",
        {"reviewer": "test"},
    )
    assert first.status_code == 200
    first_url = first.json()["artifact"]["published_url"]

    # Second approve → 200 + 'already published; no-op' detail
    second = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/approve",
        {"reviewer": "test"},
    )
    assert second.status_code == 200
    assert second.json()["artifact"]["status"] == "published"
    # published_url unchanged
    assert second.json()["artifact"]["published_url"] == first_url
    assert "already published" in (second.json().get("detail") or "")


# ═════════════════════════════════════════════════════════════════
# 12. Integration: rejecting a published artifact returns 409
# ═════════════════════════════════════════════════════════════════

def test_reject_endpoint_409_on_published(admin_api):
    if os.environ.get("BASIS_ENGINE_TEST_MODE", "").lower() not in ("1", "true", "yes"):
        pytest.skip("BASIS_ENGINE_TEST_MODE required.")

    body = {
        "entity": "drift",
        "event_date": "2026-06-04",
        "peer_set": ["jupiter-perpetual-exchange"],
    }
    resp = admin_api.post("/api/engine/analyze", body)
    assert resp.status_code == 202, resp.text[:400]
    aid = _track(resp.json()["analysis_id"])

    full = _wait_for_draft(admin_api, aid)
    assert full.get("status") == "draft"

    artifact = _render_default_artifact(admin_api, aid)
    artifact_id = artifact["id"]

    approve_resp = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/approve",
        {"reviewer": "test"},
    )
    assert approve_resp.status_code == 200

    reject_resp = admin_api.post(
        f"/api/engine/artifacts/{artifact_id}/reject",
        {"reviewer": "test", "notes": "wrong, take it back"},
    )
    assert reject_resp.status_code == 409
    detail = reject_resp.json().get("detail", {})
    if isinstance(detail, dict):
        assert detail.get("error") == "invalid_state_for_reject"
