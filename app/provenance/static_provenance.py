"""
Static Component Provenance — Python Integration
==================================================
Bridges the Rust basis-provenance service with the Python API and worker.

Responsibilities:
  1. Run the Rust prover binary (or HTTP-only self-attestation fallback)
  2. Update static_evidence records with proof paths
  3. Compute combined evidence hashes
  4. Weekly scheduling gate

The Rust binary handles:
  - TLSNotary MPC-TLS sessions (per-category strategy)
  - R2 proof upload
  - secp256k1 self-attestation

This module handles:
  - DB record creation/update
  - Evidence hash computation
  - Worker integration
  - API data retrieval
"""

import hashlib
import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from app.database import execute, fetch_all, fetch_one

logger = logging.getLogger(__name__)

# Path to the Rust binary (built from basis-provenance/)
PROVER_BINARY = os.environ.get(
    "PROVENANCE_BINARY",
    os.path.join(os.path.dirname(__file__), "..", "..", "basis-provenance", "target", "release", "basis-provenance"),
)

PROVER_CONFIG = os.environ.get(
    "PROVENANCE_CONFIG",
    os.path.join(os.path.dirname(__file__), "..", "..", "basis-provenance", "static_sources.yaml"),
)

# Weekly interval (168 hours = 7 days)
STATIC_PROVENANCE_INTERVAL_HOURS = int(
    os.environ.get("STATIC_PROVENANCE_INTERVAL_HOURS", "168")
)


# =============================================================================
# Weekly scheduling gate
# =============================================================================

def should_run_static_provenance() -> bool:
    """Check whether the weekly static provenance capture should run.

    Uses the most recent proof_captured_at across all static_evidence rows.
    Returns True if no proofs exist or the newest is older than the interval.
    """
    try:
        row = fetch_one(
            "SELECT MAX(proof_captured_at) AS latest FROM static_evidence"
        )
    except Exception:
        # Table may not exist yet
        return True

    if not row or not row.get("latest"):
        return True

    latest = row["latest"]
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=timezone.utc)

    age_hours = (datetime.now(timezone.utc) - latest).total_seconds() / 3600
    return age_hours >= STATIC_PROVENANCE_INTERVAL_HOURS


# =============================================================================
# Run the prover
# =============================================================================

def run_static_provenance_capture(
    category: Optional[str] = None,
    entity: Optional[str] = None,
) -> dict:
    """Run the static provenance capture pipeline.

    Attempts to run the Rust binary first. If unavailable, falls back to
    the Python HTTP-only self-attestation mode.

    Returns a summary dict with counts and any errors.
    """
    if os.path.isfile(PROVER_BINARY):
        return _run_rust_prover(category, entity)
    else:
        logger.info("Rust prover binary not found, using Python HTTP fallback")
        return _run_python_fallback(category, entity)


def _run_rust_prover(
    category: Optional[str] = None,
    entity: Optional[str] = None,
) -> dict:
    """Invoke the Rust basis-provenance binary and parse results."""
    cmd = [PROVER_BINARY, "--config", PROVER_CONFIG, "--json", "--register"]

    if category:
        cmd.extend(["--category", category])
    if entity:
        cmd.extend(["--entity", entity])

    logger.info(f"Running Rust prover: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10-minute timeout for full run
        )

        if result.returncode != 0 and not result.stdout:
            logger.error(f"Prover failed: {result.stderr}")
            return {"status": "error", "error": result.stderr}

        # Parse JSON output
        summary = json.loads(result.stdout)
        _process_proof_results(summary)
        return summary

    except subprocess.TimeoutExpired:
        logger.error("Prover timed out after 600s")
        return {"status": "error", "error": "timeout"}
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Prover execution error: {e}")
        return {"status": "error", "error": str(e)}


def _run_python_fallback(
    category: Optional[str] = None,
    entity: Optional[str] = None,
) -> dict:
    """Python HTTP-only fallback — fetches sources and self-attests.

    Does NOT generate TLSNotary proofs, only HTTP-fetch + hash + sign.
    This is useful for development and when the Rust binary isn't built.
    """
    import hashlib

    import httpx
    import yaml

    config_path = PROVER_CONFIG
    if not os.path.isfile(config_path):
        logger.warning(f"Config file not found: {config_path}")
        return {"status": "error", "error": "config not found"}

    with open(config_path) as f:
        config = yaml.safe_load(f)

    sources = config.get("static_sources", [])

    # Apply filters
    if category:
        sources = [s for s in sources if s.get("category") == category]
    if entity:
        sources = [s for s in sources if s.get("entity") == entity]

    results = []
    successful = 0
    failed = 0

    for source in sources:
        try:
            result = _fetch_and_attest(source)
            results.append(result)
            if result.get("status") == "success":
                successful += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Failed to fetch {source.get('url')}: {e}")
            results.append({
                "url": source.get("url"),
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    summary = {
        "status": "completed",
        "total_sources": len(sources),
        "successful": successful,
        "failed": failed,
        "results": results,
    }

    _process_proof_results(summary)
    return summary


def _fetch_and_attest(source: dict) -> dict:
    """Fetch a single source via HTTP and create a self-attestation record."""
    import httpx

    url = source["url"]
    cat = source.get("category", "html_docs")
    max_bytes = source.get("max_bytes", 16384)
    method = source.get("method", "GET").upper()

    headers = {"User-Agent": "basis-provenance/0.8"}

    # Apply Range header for html_docs and pdf_document categories
    if source.get("range_header") or cat in ("html_docs", "pdf_document"):
        if method != "HEAD":
            headers["Range"] = f"bytes=0-{max_bytes - 1}"

    # GitHub API headers
    if cat == "github_api":
        headers["Accept"] = "application/vnd.github.v3+json"
        gh_token = os.environ.get("GITHUB_TOKEN")
        if gh_token:
            headers["Authorization"] = f"Bearer {gh_token}"

    with httpx.Client(timeout=30) as client:
        if method == "HEAD":
            resp = client.head(url, headers=headers, follow_redirects=True)
            body = b""
        else:
            resp = client.get(url, headers=headers, follow_redirects=True)
            body = resp.content[:max_bytes]

    response_hash = "0x" + hashlib.sha256(body).hexdigest()
    captured_range = f"0-{len(body) - 1}" if body else "head_only"

    now = datetime.now(timezone.utc)

    return {
        "url": url,
        "entity": source.get("entity"),
        "index_id": source.get("index_id"),
        "components": source.get("components", []),
        "category": cat,
        "status": "success",
        "response_hash": response_hash,
        "http_status": resp.status_code,
        "captured_range": captured_range,
        "response_size_bytes": len(body),
        "proved_at": now.isoformat(),
    }


# =============================================================================
# DB integration — update static_evidence records
# =============================================================================

def _process_proof_results(summary: dict) -> None:
    """Process proof results and update static_evidence DB records."""
    results = summary.get("results", [])

    for result in results:
        status = result.get("status")
        if status not in ("success", "Success", "PartialSuccess"):
            continue

        # Update each component from this source
        components = result.get("components") or result.get("components_proved", [])
        for component in components:
            _upsert_static_evidence(result, component)

    # Run state attestation for the batch
    try:
        from app.state_attestation import attest_state

        evidence_records = [
            {
                "url": r.get("url"),
                "entity": r.get("entity"),
                "response_hash": r.get("response_hash"),
                "proved_at": r.get("proved_at"),
            }
            for r in results
            if r.get("status") in ("success", "Success", "PartialSuccess")
        ]
        if evidence_records:
            attest_state("static_evidence", evidence_records)
    except Exception as e:
        logger.warning(f"Failed to attest static evidence batch: {e}")


def _upsert_static_evidence(result: dict, component: str) -> None:
    """Insert or update a static_evidence record with proof data."""
    try:
        proof_result = result.get("proof_result") or result

        execute(
            """
            INSERT INTO static_evidence
                (index_id, entity_slug, component_name, source_url, source_category,
                 proof_r2_path, proof_captured_at, proof_attestation_hash,
                 proof_response_hash, proof_captured_range, proof_http_status,
                 proof_size_bytes, attestor_pubkey, last_checked_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (index_id, entity_slug, component_name)
            DO UPDATE SET
                proof_r2_path = EXCLUDED.proof_r2_path,
                proof_captured_at = EXCLUDED.proof_captured_at,
                proof_attestation_hash = EXCLUDED.proof_attestation_hash,
                proof_response_hash = EXCLUDED.proof_response_hash,
                proof_captured_range = EXCLUDED.proof_captured_range,
                proof_http_status = EXCLUDED.proof_http_status,
                proof_size_bytes = EXCLUDED.proof_size_bytes,
                attestor_pubkey = EXCLUDED.attestor_pubkey,
                last_checked_at = NOW(),
                updated_at = NOW()
            """,
            (
                result.get("index_id", ""),
                result.get("entity", ""),
                component,
                result.get("url", result.get("source_url", "")),
                result.get("category", ""),
                proof_result.get("proof_url"),
                proof_result.get("proved_at"),
                proof_result.get("attestation_hash"),
                proof_result.get("response_hash"),
                proof_result.get("captured_range"),
                proof_result.get("http_status"),
                proof_result.get("proof_size_bytes"),
                proof_result.get("attestor_pubkey"),
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to upsert static_evidence for {component}: {e}")


# =============================================================================
# Evidence hash computation
# =============================================================================

def compute_evidence_hash(
    proof_data: bytes,
    screenshot_data: bytes,
    snapshot_data: bytes,
) -> str:
    """Compute combined evidence hash: SHA-256(proof || screenshot || snapshot)."""
    h = hashlib.sha256()
    h.update(proof_data)
    h.update(screenshot_data)
    h.update(snapshot_data)
    return "0x" + h.hexdigest()


def update_evidence_hash(evidence_id: int, evidence_hash: str) -> None:
    """Update the combined evidence hash for a static_evidence record."""
    execute(
        "UPDATE static_evidence SET evidence_hash = %s, updated_at = NOW() WHERE id = %s",
        (evidence_hash, evidence_id),
    )


# =============================================================================
# Query helpers — used by API endpoints
# =============================================================================

def get_static_evidence(index_id: str, entity_slug: str, component_name: str) -> Optional[dict]:
    """Retrieve a single static evidence record."""
    row = fetch_one(
        """
        SELECT * FROM static_evidence
        WHERE index_id = %s AND entity_slug = %s AND component_name = %s
        """,
        (index_id, entity_slug, component_name),
    )
    return dict(row) if row else None


def get_entity_evidence(index_id: str, entity_slug: str) -> list[dict]:
    """Retrieve all static evidence records for an entity."""
    rows = fetch_all(
        """
        SELECT * FROM static_evidence
        WHERE index_id = %s AND entity_slug = %s
        ORDER BY component_name
        """,
        (index_id, entity_slug),
    )
    return [dict(r) for r in rows]


def get_evidence_summary() -> dict:
    """Summary statistics for all static evidence."""
    total = fetch_one("SELECT COUNT(*) AS cnt FROM static_evidence")
    with_proof = fetch_one(
        "SELECT COUNT(*) AS cnt FROM static_evidence WHERE proof_r2_path IS NOT NULL"
    )
    stale = fetch_one(
        """
        SELECT COUNT(*) AS cnt FROM static_evidence
        WHERE last_checked_at < NOW() - (check_interval_hours || ' hours')::INTERVAL
        """
    )

    return {
        "total_components": total["cnt"] if total else 0,
        "with_proof": with_proof["cnt"] if with_proof else 0,
        "stale": stale["cnt"] if stale else 0,
    }
