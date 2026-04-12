"""
Cross-Domain Coherence Sweep
==============================
Validates that attested state across all 13 domains is internally
consistent and current.  Observe-only — annotates, never gates.

Checks:
  1. Freshness gaps — each domain within expected frequency
  2. Record count drift — >20% drop flags silent source failure
  3. Cross-domain timestamp alignment — SII/PSI cycle synchronisation
  4. State root coverage — all 13 domains represented in latest pulse
"""

import json
import logging
from datetime import datetime, timezone

from app.database import fetch_one, fetch_all, execute

logger = logging.getLogger(__name__)

# ── Domain expected frequencies (hours) ──────────────────────────────────────

DOMAIN_FREQUENCIES: dict[str, float] = {
    "sii_components": 2,
    "psi_components": 2,
    "edges": 24,
    "cda_extractions": 48,
    "wallets": 4,
    "wallet_profiles": 4,
    "actors": 4,
    "discovery_signals": 4,
    "flows": 4,
    "smart_contracts": 4,
    "psi_discoveries": 48,
    "cqi_compositions": 4,
    "provenance": 4,
}

ALL_DOMAINS = list(DOMAIN_FREQUENCIES.keys())

# Domains where per-entity record_count drift is meaningful
ENTITY_SCOPE_DOMAINS = {"sii_components", "psi_components", "flows", "smart_contracts", "edges"}


# ── Individual checks ────────────────────────────────────────────────────────

def _check_freshness_gaps(now: datetime) -> list[dict]:
    """Check 1: flag domains whose latest attestation exceeds expected frequency."""
    issues = []
    for domain, max_hours in DOMAIN_FREQUENCIES.items():
        row = fetch_one(
            """SELECT MAX(cycle_timestamp) AS latest
               FROM state_attestations WHERE domain = %s""",
            (domain,),
        )
        if not row or not row.get("latest"):
            issues.append({
                "domain": domain,
                "issue_type": "freshness_gap",
                "severity": "critical",
                "description": f"No attestation found for domain '{domain}'",
                "values": {"expected_hours": max_hours, "actual_hours": None},
            })
            continue

        latest = row["latest"]
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        gap_hours = (now - latest).total_seconds() / 3600

        if gap_hours > max_hours:
            severity = "critical" if gap_hours > max_hours * 3 else "warning"
            issues.append({
                "domain": domain,
                "issue_type": "freshness_gap",
                "severity": severity,
                "description": (
                    f"Domain '{domain}' last attested {gap_hours:.1f}h ago "
                    f"(expected every {max_hours}h)"
                ),
                "values": {"expected_hours": max_hours, "actual_hours": round(gap_hours, 2)},
            })
    return issues


def _check_record_count_drift() -> list[dict]:
    """Check 2: flag >20% record_count drop between consecutive cycles."""
    issues = []
    for domain in ENTITY_SCOPE_DOMAINS:
        rows = fetch_all(
            """SELECT record_count, cycle_timestamp
               FROM state_attestations
               WHERE domain = %s AND entity_id IS NULL
               ORDER BY cycle_timestamp DESC LIMIT 2""",
            (domain,),
        )
        if not rows or len(rows) < 2:
            continue

        current_count = rows[0]["record_count"]
        previous_count = rows[1]["record_count"]

        if previous_count and previous_count > 0:
            drop_pct = (previous_count - current_count) / previous_count * 100
            if drop_pct > 20:
                issues.append({
                    "domain": domain,
                    "issue_type": "record_count_drift",
                    "severity": "critical" if drop_pct > 50 else "warning",
                    "description": (
                        f"Domain '{domain}' record count dropped {drop_pct:.1f}% "
                        f"({previous_count} → {current_count})"
                    ),
                    "values": {
                        "previous_count": previous_count,
                        "current_count": current_count,
                        "drop_pct": round(drop_pct, 1),
                    },
                })
    return issues


def _check_cross_domain_alignment(now: datetime) -> list[dict]:
    """Check 3: SII and PSI components should be attested within the same cycle window."""
    issues = []
    sii_row = fetch_one(
        "SELECT MAX(cycle_timestamp) AS latest FROM state_attestations WHERE domain = 'sii_components'"
    )
    psi_row = fetch_one(
        "SELECT MAX(cycle_timestamp) AS latest FROM state_attestations WHERE domain = 'psi_components'"
    )

    sii_ts = sii_row.get("latest") if sii_row else None
    psi_ts = psi_row.get("latest") if psi_row else None

    if not sii_ts or not psi_ts:
        return issues  # freshness check already catches missing attestations

    if sii_ts.tzinfo is None:
        sii_ts = sii_ts.replace(tzinfo=timezone.utc)
    if psi_ts.tzinfo is None:
        psi_ts = psi_ts.replace(tzinfo=timezone.utc)

    drift_hours = abs((sii_ts - psi_ts).total_seconds()) / 3600

    if drift_hours >= 3:
        stale_side = "psi_components" if sii_ts > psi_ts else "sii_components"
        fresh_side = "sii_components" if stale_side == "psi_components" else "psi_components"
        issues.append({
            "domain": stale_side,
            "issue_type": "cross_domain_alignment",
            "severity": "warning",
            "description": (
                f"'{fresh_side}' attested at {sii_ts.isoformat() if fresh_side == 'sii_components' else psi_ts.isoformat()} "
                f"but '{stale_side}' last attested at {psi_ts.isoformat() if stale_side == 'psi_components' else sii_ts.isoformat()} "
                f"({drift_hours:.1f}h drift — one scoring path may have silently failed)"
            ),
            "values": {
                "sii_latest": sii_ts.isoformat(),
                "psi_latest": psi_ts.isoformat(),
                "drift_hours": round(drift_hours, 1),
            },
        })
    return issues


def _check_state_root_coverage() -> list[dict]:
    """Check 4: verify all 13 domains are represented in the latest pulse state_root."""
    issues = []
    pulse_row = fetch_one(
        """SELECT state_root FROM daily_pulses
           ORDER BY pulse_date DESC LIMIT 1"""
    )
    if not pulse_row or not pulse_row.get("state_root"):
        issues.append({
            "domain": "pulse",
            "issue_type": "state_root_coverage",
            "severity": "warning",
            "description": "No daily pulse with state_root found",
            "values": {"missing_domains": ALL_DOMAINS},
        })
        return issues

    state_root = pulse_row["state_root"]
    if isinstance(state_root, str):
        try:
            state_root = json.loads(state_root)
        except (json.JSONDecodeError, TypeError):
            issues.append({
                "domain": "pulse",
                "issue_type": "state_root_coverage",
                "severity": "warning",
                "description": "state_root is not valid JSON",
                "values": {"raw": str(state_root)[:200]},
            })
            return issues

    # state_root may be a dict keyed by domain, or a list of domain entries
    if isinstance(state_root, dict):
        present_domains = set(state_root.keys())
    elif isinstance(state_root, list):
        present_domains = {
            entry.get("domain") for entry in state_root if isinstance(entry, dict)
        }
    else:
        present_domains = set()

    for domain in ALL_DOMAINS:
        if domain not in present_domains:
            issues.append({
                "domain": domain,
                "issue_type": "state_root_coverage",
                "severity": "warning",
                "description": f"Domain '{domain}' missing from latest pulse state_root",
                "values": {"present_domains": sorted(present_domains)},
            })
        elif isinstance(state_root, dict) and state_root.get(domain) is None:
            issues.append({
                "domain": domain,
                "issue_type": "state_root_coverage",
                "severity": "warning",
                "description": f"Domain '{domain}' has NULL entry in pulse state_root",
                "values": {"value": None},
            })

    return issues


# ── Main sweep ───────────────────────────────────────────────────────────────

def run_coherence_sweep() -> dict:
    """
    Execute all coherence checks and persist the report.
    Returns the report dict.
    """
    now = datetime.now(timezone.utc)
    all_issues: list[dict] = []

    all_issues.extend(_check_freshness_gaps(now))
    all_issues.extend(_check_record_count_drift())
    all_issues.extend(_check_cross_domain_alignment(now))
    all_issues.extend(_check_state_root_coverage())

    report = {
        "created_at": now.isoformat(),
        "domains_checked": len(ALL_DOMAINS),
        "issues_found": len(all_issues),
        "details": all_issues,
    }

    # Persist
    execute(
        """INSERT INTO coherence_reports (created_at, domains_checked, issues_found, details)
           VALUES (%s, %s, %s, %s)""",
        (now, len(ALL_DOMAINS), len(all_issues), json.dumps(all_issues, default=str)),
    )

    # Prune reports older than 30 days
    try:
        execute("DELETE FROM coherence_reports WHERE created_at < NOW() - INTERVAL '30 days'")
    except Exception:
        pass

    logger.info(
        f"Coherence sweep complete: {len(ALL_DOMAINS)} domains checked, "
        f"{len(all_issues)} issues found"
    )
    return report


# ── Query helpers (for API) ──────────────────────────────────────────────────

def get_latest_report() -> dict | None:
    """Return the most recent coherence report."""
    row = fetch_one(
        """SELECT id, created_at, domains_checked, issues_found, details
           FROM coherence_reports ORDER BY created_at DESC LIMIT 1"""
    )
    if not row:
        return None
    return {
        "id": row["id"],
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
        "domains_checked": row["domains_checked"],
        "issues_found": row["issues_found"],
        "details": row["details"] if isinstance(row["details"], list) else json.loads(row["details"] or "[]"),
    }


def get_report_history(days: int = 7) -> list[dict]:
    """Return coherence reports from the last N days."""
    rows = fetch_all(
        """SELECT id, created_at, domains_checked, issues_found, details
           FROM coherence_reports
           WHERE created_at >= NOW() - INTERVAL '1 day' * %s
           ORDER BY created_at DESC""",
        (days,),
    )
    results = []
    for row in rows:
        results.append({
            "id": row["id"],
            "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
            "domains_checked": row["domains_checked"],
            "issues_found": row["issues_found"],
            "details": row["details"] if isinstance(row["details"], list) else json.loads(row["details"] or "[]"),
        })
    return results
