"""
Load crisis_replays/ on-disk content into the `crisis_replays` Postgres table.

Run after `python scripts/generate_crisis_replays.py` (or after editing any
on-disk inputs.json/result.json) to refresh the DB. Idempotent — uses the
unique key on (crisis_slug, index_kind, entity_slug, methodology_version).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.database import execute, fetch_all

logger = logging.getLogger(__name__)

REPLAY_ROOT = Path(__file__).resolve().parent.parent / "crisis_replays"


def load_all_into_db() -> int:
    """Insert every replay directory into the DB. Returns rows written."""
    if not REPLAY_ROOT.exists():
        logger.warning("crisis_replays directory not found: %s", REPLAY_ROOT)
        return 0

    written = 0
    for rdir in sorted(REPLAY_ROOT.iterdir()):
        if not rdir.is_dir():
            continue
        inputs_path = rdir / "inputs.json"
        result_path = rdir / "result.json"
        if not (inputs_path.exists() and result_path.exists()):
            continue

        with inputs_path.open() as f:
            inputs = json.load(f)
        with result_path.open() as f:
            result = json.load(f)

        execute(
            """
            INSERT INTO crisis_replays
                (crisis_slug, crisis_label, crisis_date, index_kind, entity_slug,
                 methodology_version, input_vector_hash, computation_hash,
                 input_summary, final_score, final_grade, component_scores,
                 pre_crisis_score, delta, replay_script_path, notes)
            VALUES (%s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s::jsonb, %s, %s, %s::jsonb,
                    %s, %s, %s, %s)
            ON CONFLICT (crisis_slug, index_kind, entity_slug, methodology_version)
            DO UPDATE SET
                input_vector_hash = EXCLUDED.input_vector_hash,
                computation_hash  = EXCLUDED.computation_hash,
                final_score       = EXCLUDED.final_score,
                final_grade       = EXCLUDED.final_grade,
                pre_crisis_score  = EXCLUDED.pre_crisis_score,
                delta             = EXCLUDED.delta,
                input_summary     = EXCLUDED.input_summary,
                computed_at       = NOW()
            """,
            (
                result.get("crisis_slug"),
                result.get("crisis_label"),
                result.get("crisis_date"),
                result.get("index_kind"),
                result.get("entity_slug"),
                result.get("methodology_version"),
                result.get("input_vector_hash"),
                result.get("computation_hash"),
                json.dumps(inputs.get("components", {})),
                result.get("final_score"),
                result.get("final_grade"),
                json.dumps({}),
                result.get("pre_crisis_score"),
                result.get("delta"),
                f"crisis_replays/{rdir.name}/replay.py",
                result.get("summary"),
            ),
        )
        written += 1
    logger.info("crisis_replays loaded: %d", written)
    return written


def list_db_replays() -> list[dict]:
    rows = fetch_all(
        """
        SELECT crisis_slug, crisis_label, crisis_date, index_kind, entity_slug,
               methodology_version, final_score, final_grade,
               pre_crisis_score, delta, input_vector_hash, computation_hash,
               replay_script_path
        FROM crisis_replays
        ORDER BY crisis_date DESC
        """
    )
    return [dict(r) for r in (rows or [])]
