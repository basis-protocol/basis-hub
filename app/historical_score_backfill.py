"""
Retroactive Backfill with Confidence Surface (Bucket A3)
=========================================================

For every entity scored by PSI, RPI, LSTI, BRI, DOHI, VSRI, CXRI, TTI,
walks the entity's deployment history forward at weekly intervals and
reconstructs each weekly score from the data that was available at that
moment in time.

Each historical score row carries:
    - the input vector (full set of components used)
    - the input vector hash (sha256 of canonical serialization)
    - the computation hash (sha256 binding inputs to method version)
    - a confidence tag derived from coverage_pct:

        coverage >= 80%   -> high
        coverage >= 60%   -> medium
        coverage >= 40%   -> low
        coverage >= 20%   -> sparse
        coverage <  20%   -> bootstrap   (entity is too young to score)

This is the verifiable continuous historical series.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from app.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)


# index_kind -> (definition module, dict-name)
DEFINITION_MAP = {
    "psi":  ("app.index_definitions.psi_v01",  "PSI_V01_DEFINITION"),
    "rpi":  ("app.index_definitions.rpi_v2",   "RPI_V2_DEFINITION"),
    "lsti": ("app.index_definitions.lsti_v01", "LSTI_V01_DEFINITION"),
    "bri":  ("app.index_definitions.bri_v01",  "BRI_V01_DEFINITION"),
    "dohi": ("app.index_definitions.dohi_v01", "DOHI_V01_DEFINITION"),
    "vsri": ("app.index_definitions.vsri_v01", "VSRI_V01_DEFINITION"),
    "cxri": ("app.index_definitions.cxri_v01", "CXRI_V01_DEFINITION"),
    "tti":  ("app.index_definitions.tti_v01",  "TTI_V01_DEFINITION"),
}


def _serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_serialize)
    return "0x" + hashlib.sha256(blob.encode()).hexdigest()


def _load_definition(index_kind: str) -> dict:
    module_path, attr = DEFINITION_MAP[index_kind]
    mod = importlib.import_module(module_path)
    return getattr(mod, attr)


def _confidence_tag(coverage_pct: float) -> str:
    if coverage_pct >= 80:
        return "high"
    if coverage_pct >= 60:
        return "medium"
    if coverage_pct >= 40:
        return "low"
    if coverage_pct >= 20:
        return "sparse"
    return "bootstrap"


def _weekly_dates(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=7)


# ─── Source loaders ─────────────────────────────────────────────────────

def _load_psi_components_at(slug: str, snapshot: date) -> dict[str, float] | None:
    """Reconstruct PSI components available at snapshot date from history table."""
    row = fetch_one(
        """
        SELECT * FROM psi_temporal_reconstructions
        WHERE protocol_slug = %s AND record_date <= %s
        ORDER BY record_date DESC LIMIT 1
        """,
        (slug, snapshot),
    )
    if not row:
        return None
    skip = {"id", "protocol_slug", "record_date", "data_source", "confidence", "created_at"}
    return {k: float(v) for k, v in row.items() if k not in skip and v is not None}


def _load_rpi_components_at(slug: str, snapshot: date) -> dict[str, float] | None:
    row = fetch_one(
        """
        SELECT * FROM historical_rpi_data
        WHERE protocol_slug = %s AND record_date <= %s
        ORDER BY record_date DESC LIMIT 1
        """,
        (slug, snapshot),
    )
    if not row:
        return None
    skip = {"id", "protocol_slug", "record_date", "data_source", "confidence", "created_at"}
    return {k: float(v) for k, v in row.items() if k not in skip and v is not None}


def _load_generic_components_at(index_kind: str, slug: str, snapshot: date) -> dict[str, float] | None:
    """Fallback: pull from `component_readings` filtering by index/entity/date."""
    rows = fetch_all(
        """
        SELECT component_id, value
        FROM component_readings
        WHERE entity_id = %s AND collected_at <= %s
        ORDER BY collected_at DESC
        """,
        (slug, datetime.combine(snapshot, datetime.min.time(), tzinfo=timezone.utc)),
    )
    if not rows:
        return None
    seen: dict[str, float] = {}
    for r in rows:
        cid = r.get("component_id")
        if cid and cid not in seen and r.get("value") is not None:
            try:
                seen[cid] = float(r["value"])
            except (TypeError, ValueError):
                continue
    return seen or None


def _load_components_at(index_kind: str, slug: str, snapshot: date) -> dict[str, float] | None:
    if index_kind == "psi":
        out = _load_psi_components_at(slug, snapshot)
        if out:
            return out
    if index_kind == "rpi":
        out = _load_rpi_components_at(slug, snapshot)
        if out:
            return out
    return _load_generic_components_at(index_kind, slug, snapshot)


# ─── Scoring ────────────────────────────────────────────────────────────

def _score_from_components(definition: dict, components: dict[str, float]) -> dict | None:
    """Run the generic scoring engine for a single point in time."""
    try:
        from app.scoring_engine import score_entity
    except Exception as exc:
        logger.debug("scoring_engine unavailable: %s", exc)
        return None
    try:
        result = score_entity(definition, components)
    except Exception as exc:
        logger.debug("score_entity failed: %s", exc)
        return None
    if not result:
        return None
    return result


def _grade_for(score: float) -> str:
    if score >= 95: return "A+"
    if score >= 85: return "A"
    if score >= 75: return "B"
    if score >= 65: return "C"
    if score >= 55: return "D"
    return "F"


# ─── Entity discovery ───────────────────────────────────────────────────

def _entity_universe(index_kind: str) -> list[dict]:
    """Return [{slug, deployment_date}] for every entity scored by this index."""
    if index_kind == "psi":
        rows = fetch_all(
            """
            SELECT DISTINCT protocol_slug AS slug,
                   MIN(record_date) AS deployment_date
            FROM psi_temporal_reconstructions
            GROUP BY protocol_slug
            """
        )
        return [dict(r) for r in (rows or [])]
    if index_kind == "rpi":
        rows = fetch_all(
            """
            SELECT DISTINCT r.protocol_slug AS slug,
                   COALESCE(MIN(h.record_date), MIN(r.computed_at::date)) AS deployment_date
            FROM rpi_scores r
            LEFT JOIN historical_rpi_data h ON h.protocol_slug = r.protocol_slug
            GROUP BY r.protocol_slug
            """
        )
        return [dict(r) for r in (rows or [])]
    # Generic — derive from latest readings table by entity_id grouping.
    try:
        rows = fetch_all(
            """
            SELECT entity_id AS slug, MIN(collected_at)::date AS deployment_date
            FROM component_readings
            WHERE entity_id IS NOT NULL
            GROUP BY entity_id
            """
        )
        return [dict(r) for r in (rows or [])]
    except Exception:
        return []


# ─── Public API ─────────────────────────────────────────────────────────

def backfill_entity(
    index_kind: str,
    slug: str,
    deployment_date: date,
    *,
    end_date: date | None = None,
    max_weeks: int | None = None,
) -> int:
    """Backfill a single entity. Returns number of new rows written."""
    if index_kind not in DEFINITION_MAP:
        raise ValueError(f"Unknown index: {index_kind}")
    definition = _load_definition(index_kind)
    components_total = len(definition.get("components", {}))
    if components_total == 0:
        return 0

    end_date = end_date or date.today()
    written = 0
    weeks = list(_weekly_dates(deployment_date, end_date))
    if max_weeks:
        weeks = weeks[:max_weeks]

    for snapshot in weeks:
        components = _load_components_at(index_kind, slug, snapshot)
        components_available = len(components or {})
        coverage_pct = (
            (components_available / components_total) * 100.0
            if components_total > 0 else 0.0
        )
        confidence = _confidence_tag(coverage_pct)

        score_val: float | None = None
        grade_val: str | None = None
        component_scores: dict | None = None
        if components and confidence != "bootstrap":
            result = _score_from_components(definition, components)
            if result:
                score_val = float(result.get("overall_score") or 0)
                grade_val = result.get("grade") or _grade_for(score_val)
                component_scores = result.get("component_scores")

        input_vector = {
            "components": components or {},
            "snapshot_date": snapshot.isoformat(),
            "methodology_version": definition.get("version"),
        }
        input_hash = _canonical_hash(input_vector)
        comp_hash = _canonical_hash({
            "input_hash": input_hash,
            "methodology": definition.get("version"),
            "score": score_val,
            "grade": grade_val,
        })
        weeks_since = (snapshot - deployment_date).days // 7

        existing = fetch_one(
            """
            SELECT id FROM historical_score_backfill
            WHERE index_kind = %s AND entity_slug = %s
              AND snapshot_date = %s AND methodology_version = %s
            """,
            (index_kind, slug, snapshot, definition.get("version")),
        )
        if existing:
            continue

        execute(
            """
            INSERT INTO historical_score_backfill
                (index_kind, entity_slug, snapshot_date, deployment_date,
                 weeks_since_deployment, score, grade, methodology_version,
                 component_scores, components_available, components_total,
                 coverage_pct, confidence_tag, input_vector,
                 input_vector_hash, computation_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (index_kind, entity_slug, snapshot_date, methodology_version) DO NOTHING
            """,
            (
                index_kind, slug, snapshot, deployment_date, weeks_since,
                score_val, grade_val, definition.get("version"),
                json.dumps(component_scores or {}, default=_serialize),
                components_available, components_total,
                round(coverage_pct, 2), confidence,
                json.dumps(input_vector, default=_serialize),
                input_hash, comp_hash,
            ),
        )
        written += 1
    return written


def backfill_index(index_kind: str, *, max_entities: int | None = None,
                   max_weeks_per_entity: int | None = None) -> dict[str, int]:
    """Backfill every known entity for an index. Returns counts per entity."""
    universe = _entity_universe(index_kind)
    if max_entities:
        universe = universe[:max_entities]
    out: dict[str, int] = {}
    for entry in universe:
        slug = entry.get("slug")
        dep = entry.get("deployment_date")
        if not slug or not dep:
            continue
        if isinstance(dep, datetime):
            dep = dep.date()
        try:
            n = backfill_entity(index_kind, slug, dep, max_weeks=max_weeks_per_entity)
            out[slug] = n
        except Exception as exc:
            logger.warning("backfill failed for %s/%s: %s", index_kind, slug, exc)
            out[slug] = 0
    return out


def backfill_all(*, max_entities: int | None = None,
                 max_weeks_per_entity: int | None = None) -> dict[str, dict[str, int]]:
    """Backfill every supported index. Returns nested counts."""
    return {
        kind: backfill_index(kind, max_entities=max_entities,
                             max_weeks_per_entity=max_weeks_per_entity)
        for kind in DEFINITION_MAP.keys()
    }


def get_series(index_kind: str, slug: str) -> list[dict]:
    """Return the full historical series for an entity (for /api access)."""
    rows = fetch_all(
        """
        SELECT snapshot_date, score, grade, coverage_pct, confidence_tag,
               input_vector_hash, computation_hash, methodology_version
        FROM historical_score_backfill
        WHERE index_kind = %s AND entity_slug = %s
        ORDER BY snapshot_date ASC
        """,
        (index_kind, slug),
    )
    return [dict(r) for r in (rows or [])]


def get_input_vector(index_kind: str, slug: str, snapshot_date: date) -> dict | None:
    row = fetch_one(
        """
        SELECT input_vector, input_vector_hash, computation_hash,
               methodology_version, score, grade, coverage_pct, confidence_tag
        FROM historical_score_backfill
        WHERE index_kind = %s AND entity_slug = %s AND snapshot_date = %s
        ORDER BY methodology_version DESC LIMIT 1
        """,
        (index_kind, slug, snapshot_date),
    )
    return dict(row) if row else None
