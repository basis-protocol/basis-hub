"""
Governance Config Change Detector
==================================
Captures governance config snapshots for PSI-scored protocols and detects
changes between scoring intervals. Turns admin_key_risk from a static
assessment into a temporal signal.

Produces the `governance_stability` PSI component (0-100).
"""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta

from app.database import execute, fetch_all, fetch_one
from app.collectors.psi_collector import (
    get_solana_program_authority,
    SOLANA_PROGRAM_IDS,
    _PROTOCOL_ADMIN_SCORES,
    PROTOCOL_CONTRACTS,
)

logger = logging.getLogger(__name__)


def _build_governance_config(slug: str) -> dict | None:
    """Build a governance config snapshot for a protocol.

    For Solana protocols: queries on-chain upgrade authority via Helius.
    For EVM protocols: captures known contract/admin configuration.
    Returns a dict with the config, or None if unavailable.
    """
    config = {
        "protocol_slug": slug,
        "chain": "unknown",
        "upgrade_authority": None,
        "multisig_threshold": None,
        "timelock_seconds": None,
    }

    if slug in SOLANA_PROGRAM_IDS:
        config["chain"] = "solana"
        authority_info = get_solana_program_authority(SOLANA_PROGRAM_IDS[slug])
        if authority_info:
            config["upgrade_authority"] = authority_info.get("authority")
            config["upgradeable"] = authority_info.get("upgradeable", False)
        else:
            # Helius unavailable — use static info
            config["upgrade_authority"] = "unknown"
            config["upgradeable"] = True
    elif slug in PROTOCOL_CONTRACTS:
        config["chain"] = "ethereum"
        config["upgrade_authority"] = PROTOCOL_CONTRACTS.get(slug, "unknown")
    else:
        config["chain"] = "ethereum"

    # Add static governance structure info
    admin_score = _PROTOCOL_ADMIN_SCORES.get(slug)
    if admin_score is not None:
        config["admin_risk_score"] = admin_score

    return config


def _hash_config(config: dict) -> str:
    """SHA-256 hash of the config for change detection."""
    canonical = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def capture_governance_snapshot(slug: str) -> dict | None:
    """Capture and store a governance config snapshot for a protocol.

    Returns a dict with change detection results:
    - changed: bool
    - old_config: dict or None
    - new_config: dict
    - event: dict or None (if a change was detected)
    """
    config = _build_governance_config(slug)
    if not config:
        return None

    config_hash = _hash_config(config)

    # Get most recent prior snapshot
    prior = fetch_one("""
        SELECT config_hash, raw_config, timelock_seconds
        FROM psi_governance_snapshots
        WHERE protocol_slug = %s
        ORDER BY snapshot_date DESC
        LIMIT 1
    """, (slug,))

    changed = False
    event = None

    if prior and prior["config_hash"] != config_hash:
        changed = True
        old_config = prior["raw_config"] if isinstance(prior["raw_config"], dict) else json.loads(prior["raw_config"])
        old_timelock = prior.get("timelock_seconds") or 0
        new_timelock = config.get("timelock_seconds") or 0

        # Determine severity
        severity = "warning"
        if old_timelock > 0 and new_timelock == 0:
            severity = "critical"

        # Build human-readable description
        changes = []
        if config.get("upgrade_authority") != old_config.get("upgrade_authority"):
            changes.append(
                f"{slug} upgrade authority changed from "
                f"{old_config.get('upgrade_authority', 'unknown')} to "
                f"{config.get('upgrade_authority', 'unknown')}"
            )
        if old_timelock != new_timelock:
            if new_timelock == 0:
                changes.append(f"{slug} timelock removed: was {old_timelock}s, now 0s")
            else:
                changes.append(f"{slug} timelock changed: {old_timelock}s → {new_timelock}s")
        if config.get("multisig_threshold") != old_config.get("multisig_threshold"):
            changes.append(
                f"{slug} multisig threshold changed from "
                f"{old_config.get('multisig_threshold', 'unknown')} to "
                f"{config.get('multisig_threshold', 'unknown')}"
            )
        if not changes:
            changes.append(f"{slug} governance configuration changed (config hash mismatch)")

        description = "; ".join(changes)

        # Store event in score_events table
        try:
            execute("""
                INSERT INTO score_events (event_date, event_name, event_type,
                    affected_stablecoins, description, severity)
                VALUES (CURRENT_DATE, %s, %s, %s, %s, %s)
            """, (
                f"Governance config change: {slug}",
                "governance_config_change",
                [slug],  # using affected_stablecoins for protocol slug
                description,
                severity,
            ))
            logger.warning(f"GOVERNANCE CHANGE DETECTED: {description} (severity={severity})")
        except Exception as e:
            logger.error(f"Failed to store governance change event for {slug}: {e}")

        event = {
            "protocol_slug": slug,
            "severity": severity,
            "event_type": "governance_config_change",
            "description": description,
            "old_config": old_config,
            "new_config": config,
        }

    # Store the snapshot
    try:
        execute("""
            INSERT INTO psi_governance_snapshots
                (protocol_slug, chain, config_hash, raw_config,
                 upgrade_authority, multisig_threshold, timelock_seconds)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (protocol_slug, snapshot_date)
            DO UPDATE SET
                config_hash = EXCLUDED.config_hash,
                raw_config = EXCLUDED.raw_config,
                upgrade_authority = EXCLUDED.upgrade_authority,
                multisig_threshold = EXCLUDED.multisig_threshold,
                timelock_seconds = EXCLUDED.timelock_seconds
        """, (
            slug,
            config.get("chain"),
            config_hash,
            json.dumps(config, default=str),
            config.get("upgrade_authority"),
            config.get("multisig_threshold"),
            config.get("timelock_seconds"),
        ))
    except Exception as e:
        logger.error(f"Failed to store governance snapshot for {slug}: {e}")

    return {
        "changed": changed,
        "old_config": prior["raw_config"] if prior else None,
        "new_config": config,
        "config_hash": config_hash,
        "event": event,
    }


def compute_governance_stability(slug: str) -> float:
    """Compute the governance_stability component score (0-100).

    Starts at 100, decreases based on:
    - Number of governance config changes in last 90 days: each change -20
    - No timelock: cap at 40
    - Change in last 7 days: additional -20
    """
    now = datetime.now(timezone.utc)
    ninety_days_ago = now - timedelta(days=90)
    seven_days_ago = now - timedelta(days=7)

    # Count distinct config hashes in last 90 days (changes = distinct hashes - 1)
    snapshots = fetch_all("""
        SELECT config_hash, snapshot_date, timelock_seconds
        FROM psi_governance_snapshots
        WHERE protocol_slug = %s AND snapshot_date >= %s
        ORDER BY snapshot_date ASC
    """, (slug, ninety_days_ago))

    if not snapshots:
        return 80.0  # No data — neutral score

    # Count actual changes (consecutive different hashes)
    changes_90d = 0
    changes_7d = 0
    prev_hash = None
    for snap in snapshots:
        if prev_hash and snap["config_hash"] != prev_hash:
            changes_90d += 1
            if snap["snapshot_date"] >= seven_days_ago:
                changes_7d += 1
        prev_hash = snap["config_hash"]

    # Latest snapshot for timelock check
    latest = snapshots[-1]
    has_timelock = (latest.get("timelock_seconds") or 0) > 0

    # Compute score
    score = 100.0
    score -= changes_90d * 20  # Each change -20
    if changes_7d > 0:
        score -= 20  # Recent change penalty

    # Cap if no timelock
    if not has_timelock:
        score = min(score, 40.0)

    return max(score, 0.0)


def capture_all_governance_snapshots():
    """Capture governance snapshots for all target protocols. Called during PSI scoring cycle."""
    from app.index_definitions.psi_v01 import TARGET_PROTOCOLS

    results = []
    for slug in TARGET_PROTOCOLS:
        try:
            result = capture_governance_snapshot(slug)
            if result:
                results.append(result)
                if result["changed"]:
                    logger.warning(f"  {slug}: GOVERNANCE CONFIG CHANGED")
                else:
                    logger.info(f"  {slug}: governance config unchanged")
        except Exception as e:
            logger.error(f"Failed to capture governance snapshot for {slug}: {e}")

    changes = [r for r in results if r.get("changed")]
    logger.info(f"Governance snapshots: {len(results)} captured, {len(changes)} changes detected")
    return results


def get_governance_history(slug: str) -> dict:
    """Get governance snapshot history for a protocol with diffs highlighted."""
    snapshots = fetch_all("""
        SELECT id, protocol_slug, chain, snapshot_date, config_hash,
               raw_config, upgrade_authority, multisig_threshold,
               timelock_seconds, created_at
        FROM psi_governance_snapshots
        WHERE protocol_slug = %s
        ORDER BY snapshot_date DESC
        LIMIT 100
    """, (slug,))

    events = fetch_all("""
        SELECT event_date, event_name, event_type, description, severity, created_at
        FROM score_events
        WHERE event_type = 'governance_config_change'
          AND %s = ANY(affected_stablecoins)
        ORDER BY event_date DESC
        LIMIT 50
    """, (slug,))

    # Annotate snapshots with change flags
    annotated = []
    prev_hash = None
    for snap in reversed(snapshots):  # chronological order for diff
        entry = {
            "snapshot_date": snap["snapshot_date"],
            "config_hash": snap["config_hash"],
            "upgrade_authority": snap["upgrade_authority"],
            "multisig_threshold": snap["multisig_threshold"],
            "timelock_seconds": snap["timelock_seconds"],
            "chain": snap["chain"],
            "changed": prev_hash is not None and snap["config_hash"] != prev_hash,
        }
        if isinstance(snap["raw_config"], str):
            entry["raw_config"] = json.loads(snap["raw_config"])
        else:
            entry["raw_config"] = snap["raw_config"]
        prev_hash = snap["config_hash"]
        annotated.append(entry)

    annotated.reverse()  # most recent first

    return {
        "protocol_slug": slug,
        "snapshot_count": len(annotated),
        "change_count": sum(1 for s in annotated if s["changed"]),
        "snapshots": annotated,
        "events": [dict(e) for e in events],
        "governance_stability_score": compute_governance_stability(slug),
    }
