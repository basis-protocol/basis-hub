"""
Component 2: Background tasks.

S2a: a single task `finalize_stub_analysis` that sleeps briefly and flips
a newly-inserted Analysis row from `status='pending'` to `status='draft'`.
This is the skeleton of the async state machine that S2c will replace with
real LLM-backed interpretation + cache lookup + result persistence.

Spawned via asyncio.create_task() from the async POST /analyze handler.
Runs in the same event loop as the request handler; no external queue.

Known limitation (acknowledged in Step 0 §3 and S2a prompt): in-process
tasks don't survive worker restart. If uvicorn restarts a worker between
the INSERT and the scheduled status flip, the row stays pending forever.
S2c introduces a reaper job to sweep orphaned pending rows older than
10 minutes. Deferred here because stub behavior has no cost of being
re-queued manually.

Exceptions from the background task are caught and logged via an
add_done_callback so they don't vanish silently.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.engine.analysis_persistence import update_analysis_status

logger = logging.getLogger(__name__)


# Delay used by the stub finalizer. Kept small for test ergonomics
# (test_analyze_pending_flips_to_draft waits 3 seconds, so 2 leaves
# headroom). S2c will replace this with the real LLM roundtrip time.
STUB_FINALIZE_DELAY_SECONDS = 2


async def finalize_stub_analysis(analysis_id: UUID) -> None:
    """Sleep briefly, then flip pending → draft on the given analysis.

    S2a stub implementation — no real work performed. Later stages
    will populate real Signal/Interpretation here and then flip.
    """
    await asyncio.sleep(STUB_FINALIZE_DELAY_SECONDS)
    await update_analysis_status(analysis_id, new_status="draft")


def spawn_finalize_task(analysis_id: UUID) -> asyncio.Task:
    """Schedule finalize_stub_analysis on the running event loop and
    attach a done-callback that logs exceptions. Returns the Task so
    callers can optionally await it (tests) but normally fire-and-forget."""
    task = asyncio.create_task(finalize_stub_analysis(analysis_id))

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            logger.warning(
                "finalize_stub_analysis cancelled for id=%s", analysis_id
            )
            return
        exc = t.exception()
        if exc is not None:
            logger.exception(
                "finalize_stub_analysis failed for id=%s: %s", analysis_id, exc
            )

    task.add_done_callback(_on_done)
    return task
