"""
Structured Incident Auto-Detection
=====================================
Detects incidents from existing data: score drops, peg deviations,
volume spikes, TVL crashes. Stores as structured timeline with severity.

Sources: computed from existing scored data + discovery signals

Schedule: Daily
"""

import json
import logging
from datetime import datetime, timezone

from app.database import fetch_all, fetch_one, execute, fetch_one_async, fetch_all_async, execute_async

logger = logging.getLogger(__name__)

# Detection rules
INCIDENT_RULES = [
    {
        "name": "score_crash",
        "entity_type": "stablecoin",
        "query": """
            SELECT h1.stablecoin as entity_id,
                   h1.overall_score as current_score,
                   h2.overall_score as previous_score,
                   h1.overall_score - h2.overall_score as drop
            FROM score_history h1
            JOIN score_history h2
                ON h1.stablecoin = h2.stablecoin
                AND h2.score_date = h1.score_date - 1
            WHERE h1.score_date = CURRENT_DATE
              AND (h1.overall_score - h2.overall_score) < -10
        """,
        "incident_type": "score_crash",
        "severity_fn": lambda row: "critical" if row["drop"] < -20 else "high",
        "title_fn": lambda row: f"Score crash: {row['entity_id']} dropped {abs(row['drop']):.1f} points",
        "description_fn": lambda row: (
            f"SII score dropped from {row['previous_score']:.1f} to {row['current_score']:.1f} "
            f"({row['drop']:.1f} points) in 24 hours"
        ),
    },
    {
        "name": "peg_deviation",
        "entity_type": "stablecoin",
        "query": """
            SELECT stablecoin_id as entity_id,
                   MAX(deviation_bps) as max_deviation_bps,
                   COUNT(*) as deviation_count
            FROM peg_snapshots_5m
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
              AND deviation_bps > 100
            GROUP BY stablecoin_id
            HAVING COUNT(*) >= 6
        """,
        "incident_type": "depeg",
        "severity_fn": lambda row: (
            "critical" if row["max_deviation_bps"] > 500
            else "high" if row["max_deviation_bps"] > 200
            else "medium"
        ),
        "title_fn": lambda row: f"Peg deviation: {row['entity_id']} ({row['max_deviation_bps']:.0f}bps max)",
        "description_fn": lambda row: (
            f"Sustained peg deviation: {row['deviation_count']} observations >100bps in 24h, "
            f"max deviation {row['max_deviation_bps']:.0f}bps"
        ),
    },
    {
        "name": "tvl_crash",
        "entity_type": "protocol",
        "query": """
            SELECT y1.protocol as entity_id,
                   y1.tvl_usd as current_tvl,
                   y2.tvl_usd as previous_tvl,
                   CASE WHEN y2.tvl_usd > 0
                        THEN ((y1.tvl_usd - y2.tvl_usd) / y2.tvl_usd * 100)
                        ELSE 0 END as change_pct
            FROM (
                SELECT protocol, SUM(tvl_usd) as tvl_usd
                FROM yield_snapshots
                WHERE snapshot_at >= NOW() - INTERVAL '2 hours'
                GROUP BY protocol
            ) y1
            JOIN (
                SELECT protocol, SUM(tvl_usd) as tvl_usd
                FROM yield_snapshots
                WHERE snapshot_at BETWEEN NOW() - INTERVAL '26 hours' AND NOW() - INTERVAL '22 hours'
                GROUP BY protocol
            ) y2 ON y1.protocol = y2.protocol
            WHERE y2.tvl_usd > 1000000
              AND ((y1.tvl_usd - y2.tvl_usd) / y2.tvl_usd * 100) < -30
        """,
        "incident_type": "tvl_crash",
        "severity_fn": lambda row: "critical" if row["change_pct"] < -50 else "high",
        "title_fn": lambda row: f"TVL crash: {row['entity_id']} ({row['change_pct']:.0f}%)",
        "description_fn": lambda row: (
            f"Protocol TVL dropped {abs(row['change_pct']):.1f}% in 24h "
            f"(${row['previous_tvl']:,.0f} → ${row['current_tvl']:,.0f})"
        ),
    },
    {
        "name": "redemption_spike",
        "entity_type": "stablecoin",
        "query": """
            SELECT stablecoin_id as entity_id,
                   COUNT(*) as burn_count,
                   SUM(amount) as total_burned
            FROM mint_burn_events
            WHERE event_type = 'burn'
              AND amount >= 1000000
              AND timestamp >= NOW() - INTERVAL '6 hours'
            GROUP BY stablecoin_id
            HAVING COUNT(*) >= 5
        """,
        "incident_type": "redemption_spike",
        "severity_fn": lambda row: "critical" if row["total_burned"] > 100_000_000 else "high",
        "title_fn": lambda row: f"Redemption spike: {row['entity_id']} ({row['burn_count']} large burns)",
        "description_fn": lambda row: (
            f"{row['burn_count']} burns >$1M in last 6 hours, "
            f"total ${row['total_burned']:,.0f} redeemed"
        ),
    },
]


async def run_incident_detection() -> dict:
    """
    Run all incident detection rules.
    For each detected incident, store in incident_events table.
    """
    total_detected = 0
    results = {}

    for rule in INCIDENT_RULES:
        try:
            rows = await fetch_all_async(rule["query"])
            if not rows:
                results[rule["name"]] = 0
                continue

            for row in rows:
                entity_id = row["entity_id"]
                severity = rule["severity_fn"](row)
                title = rule["title_fn"](row)
                description = rule["description_fn"](row)

                # Check if already recorded recently
                existing = await fetch_one_async(
                    """SELECT id FROM incident_events
                       WHERE entity_id = %s AND incident_type = %s
                         AND created_at >= NOW() - INTERVAL '24 hours'""",
                    (entity_id, rule["incident_type"]),
                )
                if existing:
                    continue

                await execute_async(
                    """INSERT INTO incident_events
                       (entity_id, entity_type, incident_type, severity,
                        title, description, started_at,
                        detection_method, raw_data, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'automated', %s, NOW())
                       ON CONFLICT (entity_id, incident_type, started_at) DO NOTHING""",
                    (
                        entity_id, rule["entity_type"], rule["incident_type"],
                        severity, title, description,
                        json.dumps({k: float(v) if isinstance(v, (int, float)) else str(v) for k, v in dict(row).items()}),
                    ),
                )
                total_detected += 1

            results[rule["name"]] = len(rows)

        except Exception as e:
            logger.debug(f"Incident rule {rule['name']} failed: {e}")
            results[rule["name"]] = f"error: {str(e)}"

    logger.info(f"Incident detection complete: {total_detected} new incidents")
    return {"incidents_detected": total_detected, "rules": results}
