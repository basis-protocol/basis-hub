"""
Component 5: Git commit operations.

When the operator approves an artifact, its rendered markdown lands in
basis-protocol/basis-hub at the path the renderer suggested. This module
owns the clone-write-commit-push dance via subprocess so we don't pull
in GitPython for one workflow.

Public entry: commit_artifact(artifact) → CommitResult
  - On success: status='committed', commit_url='https://github.com/...'
  - On TEST_MODE: status='committed', commit_url='.../test-mode/...'
  - On failure: status='failed', detail explains the stage
  - When BASIS_ENGINE_TEST_MODE=1, no shell-out happens at all.

Concurrency: GitHub doesn't fail two near-simultaneous pushes on
unrelated paths but our local clone certainly does (a stale ref between
two workers walking through clone → write → push will produce a
non-fast-forward push). We serialize commits with a module-level
asyncio.Lock so concurrent approvals are safe within a single process.
Cross-worker safety would need a DB lock — out of scope for v1; current
deployment runs a single uvicorn worker.

PAT redaction: when stderr from `git push` mentions the PAT (it shouldn't
— modern git reads creds from a helper — but defense in depth), the
output is scrubbed before logging or surfacing in the return value.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.engine.schemas import ArtifactResponse

logger = logging.getLogger(__name__)


_TEST_MODE_ENV = "BASIS_ENGINE_TEST_MODE"
_PAT_ENV = "BASIS_ENGINE_GITHUB_PAT"
_REPO_OWNER = "basis-protocol"
_REPO_NAME = "basis-hub"
_DEFAULT_BRANCH = "main"
_DEFAULT_AUTHOR_NAME = "Basis Engine"
_DEFAULT_AUTHOR_EMAIL = "engine@basis.foundation"

# One lock per process — see module docstring.
_COMMIT_LOCK: asyncio.Lock = asyncio.Lock()


@dataclass
class CommitResult:
    status: str  # "committed" | "failed" | "skipped"
    commit_url: Optional[str] = None
    detail: Optional[str] = None
    test_mode: bool = False


def _redact(text: str, secret: Optional[str]) -> str:
    """Scrub `secret` from `text`. No-op if secret is empty."""
    if not text:
        return text
    if not secret:
        return text
    return text.replace(secret, "***REDACTED***")


def _is_test_mode() -> bool:
    return os.environ.get(_TEST_MODE_ENV, "").strip().lower() in ("1", "true", "yes")


def _validate_relative_path(suggested_path: str, workspace: Path) -> Path:
    """Resolve `suggested_path` inside `workspace` and ensure it doesn't
    escape via .. or absolute-path tricks. Raises ValueError on rejection.
    """
    if not suggested_path:
        raise ValueError("artifact has no suggested_path; cannot commit")

    candidate = (workspace / suggested_path).resolve()
    workspace_resolved = workspace.resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError(
            f"suggested_path {suggested_path!r} resolves outside workspace"
        ) from exc
    return candidate


def _run(
    cmd: list[str],
    cwd: Path,
    secret: Optional[str],
    extra_env: Optional[dict] = None,
) -> subprocess.CompletedProcess:
    """Run a subprocess, capture both streams, redact PAT from any output
    we surface. Raises subprocess.CalledProcessError on non-zero exit so
    the caller can wrap into a CommitResult."""
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    logger.info(
        "git_commit._run: cwd=%s cmd=%s",
        cwd, " ".join(shlex.quote(c) for c in cmd),
    )
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )
    if proc.returncode != 0:
        stderr = _redact(proc.stderr or "", secret)
        stdout = _redact(proc.stdout or "", secret)
        logger.warning(
            "git_commit._run failed rc=%d cmd=%s stderr=%s stdout=%s",
            proc.returncode, cmd[0], stderr, stdout,
        )
        # Re-raise with redacted streams so the surrounding except can
        # safely include the message in CommitResult.detail.
        err = subprocess.CalledProcessError(proc.returncode, cmd, stdout, stderr)
        raise err
    return proc


def _commit_artifact_sync(artifact: ArtifactResponse) -> CommitResult:
    """The full clone-write-commit-push dance, blocking. Caller wraps
    this in asyncio.to_thread so the event loop stays free.
    """
    if _is_test_mode():
        fake_url = (
            f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/commit/"
            f"test-mode-{uuid.uuid4().hex[:12]}"
        )
        logger.info(
            "git_commit: TEST_MODE artifact_id=%s suggested_path=%s — "
            "skipping git operations, returning fake url %s",
            artifact.id, artifact.suggested_path, fake_url,
        )
        return CommitResult(
            status="committed",
            commit_url=fake_url,
            detail="test_mode bypass",
            test_mode=True,
        )

    pat = os.environ.get(_PAT_ENV, "").strip()
    if not pat:
        return CommitResult(
            status="failed",
            detail=f"{_PAT_ENV} unset; cannot push",
        )

    if not artifact.suggested_path:
        return CommitResult(
            status="failed",
            detail="artifact.suggested_path is empty; nothing to commit",
        )

    remote_url = (
        f"https://x-access-token:{pat}@github.com/"
        f"{_REPO_OWNER}/{_REPO_NAME}.git"
    )

    workdir = Path(tempfile.mkdtemp(prefix="basis-engine-commit-"))
    try:
        clone_dir = workdir / "repo"
        try:
            _run(
                ["git", "clone", "--depth", "1", "--branch", _DEFAULT_BRANCH,
                 remote_url, str(clone_dir)],
                cwd=workdir,
                secret=pat,
            )
        except subprocess.CalledProcessError as exc:
            return CommitResult(
                status="failed",
                detail=f"git clone failed: {_redact(exc.stderr or '', pat)[:300]}",
            )

        try:
            target = _validate_relative_path(artifact.suggested_path, clone_dir)
        except ValueError as exc:
            return CommitResult(status="failed", detail=str(exc))

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact.content_markdown, encoding="utf-8")

        # Configure committer identity per-clone (no global git config writes).
        for cfg in (
            ["git", "config", "user.name", _DEFAULT_AUTHOR_NAME],
            ["git", "config", "user.email", _DEFAULT_AUTHOR_EMAIL],
        ):
            try:
                _run(cfg, cwd=clone_dir, secret=pat)
            except subprocess.CalledProcessError as exc:
                return CommitResult(
                    status="failed",
                    detail=f"git config failed: {_redact(exc.stderr or '', pat)[:200]}",
                )

        try:
            _run(
                ["git", "add", artifact.suggested_path],
                cwd=clone_dir,
                secret=pat,
            )
        except subprocess.CalledProcessError as exc:
            return CommitResult(
                status="failed",
                detail=f"git add failed: {_redact(exc.stderr or '', pat)[:200]}",
            )

        # If nothing actually changed (re-approval after manual revert?),
        # skip rather than committing an empty diff.
        try:
            diff_check = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(clone_dir),
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            return CommitResult(
                status="failed", detail=f"git diff probe failed: {exc}",
            )
        if diff_check.returncode == 0:
            logger.info(
                "git_commit: artifact_id=%s produced no diff; skipping commit",
                artifact.id,
            )
            return CommitResult(
                status="skipped",
                detail="no diff vs origin/main",
            )

        commit_subject = (
            f"engine: publish {artifact.artifact_type} for analysis "
            f"{artifact.analysis_id}"
        )
        try:
            _run(
                ["git", "commit", "-m", commit_subject],
                cwd=clone_dir,
                secret=pat,
            )
        except subprocess.CalledProcessError as exc:
            return CommitResult(
                status="failed",
                detail=f"git commit failed: {_redact(exc.stderr or '', pat)[:200]}",
            )

        try:
            _run(
                ["git", "push", "origin", _DEFAULT_BRANCH],
                cwd=clone_dir,
                secret=pat,
            )
        except subprocess.CalledProcessError as exc:
            return CommitResult(
                status="failed",
                detail=f"git push failed: {_redact(exc.stderr or '', pat)[:200]}",
            )

        try:
            sha_proc = _run(
                ["git", "rev-parse", "HEAD"],
                cwd=clone_dir,
                secret=pat,
            )
            sha = (sha_proc.stdout or "").strip()
        except subprocess.CalledProcessError:
            sha = ""

        commit_url = (
            f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/commit/{sha}"
            if sha
            else f"https://github.com/{_REPO_OWNER}/{_REPO_NAME}/commits/{_DEFAULT_BRANCH}"
        )
        logger.info(
            "git_commit: pushed artifact_id=%s sha=%s path=%s",
            artifact.id, sha, artifact.suggested_path,
        )
        return CommitResult(
            status="committed",
            commit_url=commit_url,
            detail=f"pushed sha={sha[:12]}" if sha else "pushed",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def commit_artifact(artifact: ArtifactResponse) -> CommitResult:
    """Acquire the process-wide commit lock and run the sync flow.

    Lock is held across the whole clone-write-push so two parallel
    approvals don't race a non-fast-forward push.
    """
    async with _COMMIT_LOCK:
        return await asyncio.to_thread(_commit_artifact_sync, artifact)
