"""
State Growth Dashboard
=======================
Comprehensive dashboard of accumulated state across the universal data layer.
GET /api/ops/state-growth

Shows: row counts, growth rates, wallet graph growth, entity coverage,
API utilization, provenance coverage, temporal depth, data quality, storage.
"""

import logging
from datetime import datetime, timezone

from app.database import fetch_all, fetch_one

logger = logging.getLogger(__name__)

# Tables to track with their timestamp columns and avg row sizes
TRACKED_TABLES = {
    "liquidity_depth":          {"time_col": "snapshot_at",  "avg_row_bytes": 300},
    "yield_snapshots":          {"time_col": "snapshot_at",  "avg_row_bytes": 250},
    "governance_proposals":     {"time_col": "collected_at", "avg_row_bytes": 2000},
    "governance_voters":        {"time_col": "collected_at", "avg_row_bytes": 150},
    "bridge_flows":             {"time_col": "snapshot_at",  "avg_row_bytes": 200},
    "exchange_snapshots":       {"time_col": "snapshot_at",  "avg_row_bytes": 500},
    "correlation_matrices":     {"time_col": "computed_at",  "avg_row_bytes": 5000},
    "volatility_surfaces":      {"time_col": "computed_at",  "avg_row_bytes": 200},
    "incident_events":          {"time_col": "created_at",   "avg_row_bytes": 1000},
    "peg_snapshots_5m":         {"time_col": "timestamp",    "avg_row_bytes": 80},
    "mint_burn_events":         {"time_col": "collected_at", "avg_row_bytes": 300},
    "entity_snapshots_hourly":  {"time_col": "snapshot_at",  "avg_row_bytes": 1000},
    "contract_surveillance":    {"time_col": "scanned_at",   "avg_row_bytes": 2000},
    "wallet_behavior_tags":     {"time_col": "computed_at",  "avg_row_bytes": 200},
    "dex_pool_ohlcv":           {"time_col": "timestamp",    "avg_row_bytes": 150},
    "market_chart_history":     {"time_col": "timestamp",    "avg_row_bytes": 100},
    "scores":                   {"time_col": "calculated_at", "avg_row_bytes": 400},
    "score_history":            {"time_col": "created_at",   "avg_row_bytes": 300},
    "psi_scores":               {"time_col": "scored_at",    "avg_row_bytes": 300},
    "component_readings":       {"time_col": "collected_at", "avg_row_bytes": 150},
    "api_usage_tracker":        {"time_col": "recorded_at",  "avg_row_bytes": 150},
    "api_usage_hourly":         {"time_col": "hour",         "avg_row_bytes": 200},
    "coherence_violations":     {"time_col": "created_at",   "avg_row_bytes": 300},
    "protocol_pool_wallets":    {"time_col": "discovered_at", "avg_row_bytes": 100},
}


def _safe_count(query: str, params: tuple = ()) -> int:
    """Run a count query, return 0 on error."""
    try:
        row = fetch_one(query, params)
        return int(row["cnt"]) if row and row.get("cnt") else 0
    except Exception:
        return 0


def _safe_fetch(query: str, params: tuple = ()):
    try:
        return fetch_one(query, params)
    except Exception:
        return None


def get_state_growth() -> dict:
    """Comprehensive state growth dashboard."""
    now = datetime.now(timezone.utc)

    # =========================================================================
    # 1. Per-table row counts and growth
    # =========================================================================
    tables = {}
    total_rows = 0
    total_bytes = 0

    for table_name, config in TRACKED_TABLES.items():
        tc = config["time_col"]
        arb = config["avg_row_bytes"]

        row_count = _safe_count(f"SELECT COUNT(*) as cnt FROM {table_name}")
        rows_24h = _safe_count(
            f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {tc} >= NOW() - INTERVAL '24 hours'"
        )
        rows_7d = _safe_count(
            f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {tc} >= NOW() - INTERVAL '7 days'"
        )

        growth_rate = round(rows_7d / 7, 1) if rows_7d else 0
        est_monthly_bytes = growth_rate * 30 * arb

        tables[table_name] = {
            "row_count": row_count,
            "rows_24h": rows_24h,
            "rows_7d": rows_7d,
            "growth_rate_per_day": growth_rate,
            "est_monthly_mb": round(est_monthly_bytes / 1_000_000, 2),
        }

        total_rows += row_count
        total_bytes += row_count * arb

    # =========================================================================
    # 2. Wallet graph growth
    # =========================================================================
    wallet_total = _safe_count("SELECT COUNT(*) as cnt FROM wallet_graph.wallets")
    wallet_24h = _safe_count(
        "SELECT COUNT(*) as cnt FROM wallet_graph.wallets WHERE created_at >= NOW() - INTERVAL '24 hours'"
    )
    wallet_7d = _safe_count(
        "SELECT COUNT(*) as cnt FROM wallet_graph.wallets WHERE created_at >= NOW() - INTERVAL '7 days'"
    )
    wallet_30d = _safe_count(
        "SELECT COUNT(*) as cnt FROM wallet_graph.wallets WHERE created_at >= NOW() - INTERVAL '30 days'"
    )
    wallets_with_scores = _safe_count(
        "SELECT COUNT(*) as cnt FROM wallet_graph.wallet_risk_scores"
    )
    wallets_with_edges = _safe_count(
        "SELECT COUNT(DISTINCT source_address) as cnt FROM wallet_graph.wallet_edges"
    )
    wallets_with_tags = _safe_count(
        "SELECT COUNT(DISTINCT wallet_address) as cnt FROM wallet_behavior_tags"
    )

    daily_growth = round(wallet_7d / 7) if wallet_7d else 0
    days_to_500k = round((500_000 - wallet_total) / daily_growth) if daily_growth > 0 else None

    wallet_graph = {
        "total_wallets": wallet_total,
        "wallets_24h": wallet_24h,
        "wallets_7d": wallet_7d,
        "wallets_30d": wallet_30d,
        "wallets_with_scores": wallets_with_scores,
        "wallets_with_edges": wallets_with_edges,
        "wallets_with_behavior_tags": wallets_with_tags,
        "coverage_pct": round(
            min(wallets_with_scores, wallets_with_edges) / wallet_total * 100, 1
        ) if wallet_total > 0 else 0,
        "daily_growth": daily_growth,
        "target": 500_000,
        "days_to_target": days_to_500k,
    }

    # =========================================================================
    # 3. Entity coverage
    # =========================================================================
    sii_scored = _safe_count("SELECT COUNT(DISTINCT stablecoin_id) as cnt FROM scores")
    sii_total = _safe_count("SELECT COUNT(*) as cnt FROM stablecoins WHERE scoring_enabled = TRUE")
    psi_scored = _safe_count("SELECT COUNT(DISTINCT protocol_slug) as cnt FROM psi_scores")
    psi_discovered = _safe_count(
        "SELECT COUNT(*) as cnt FROM protocol_backlog WHERE enrichment_status != 'insufficient'"
    )

    entity_coverage = {
        "sii": {"scored": sii_scored, "total": sii_total},
        "psi": {"scored": psi_scored, "discovered": psi_discovered},
        "total_scored_entities": sii_scored + psi_scored,
    }

    # =========================================================================
    # 4. API utilization
    # =========================================================================
    try:
        from app.api_usage_tracker import get_realtime_counters
        api_usage = get_realtime_counters()
    except Exception:
        api_usage = {}

    # =========================================================================
    # 5. Provenance coverage
    # =========================================================================
    try:
        from app.data_layer.provenance_scaling import get_coverage_report
        provenance = get_coverage_report()
    except Exception:
        provenance = {"sources": {"total": 0, "proven": 0}}

    # =========================================================================
    # 6. Temporal depth
    # =========================================================================
    temporal = {}
    for table_name, config in TRACKED_TABLES.items():
        tc = config["time_col"]
        row = _safe_fetch(
            f"SELECT MIN({tc}) as earliest, MAX({tc}) as latest FROM {table_name}"
        )
        if row and row.get("earliest") and row.get("latest"):
            temporal[table_name] = {
                "earliest": str(row["earliest"]),
                "latest": str(row["latest"]),
            }

    # =========================================================================
    # 7. Data quality
    # =========================================================================
    coherence_flags_24h = _safe_count(
        "SELECT COUNT(*) as cnt FROM coherence_violations WHERE created_at >= NOW() - INTERVAL '24 hours'"
    )
    unreviewed_flags = _safe_count(
        "SELECT COUNT(*) as cnt FROM coherence_violations WHERE reviewed = FALSE"
    )

    # Check for stale data types
    stale_types = []
    staleness_thresholds = {
        "liquidity_depth": 3, "exchange_snapshots": 3, "entity_snapshots_hourly": 3,
        "yield_snapshots": 26, "governance_proposals": 26, "bridge_flows": 26,
        "peg_snapshots_5m": 26, "mint_burn_events": 26, "contract_surveillance": 170,
    }
    for table_name, max_hours in staleness_thresholds.items():
        tc = TRACKED_TABLES.get(table_name, {}).get("time_col", "created_at")
        latest = _safe_fetch(f"SELECT MAX({tc}) as latest FROM {table_name}")
        if latest and latest.get("latest"):
            lt = latest["latest"]
            if hasattr(lt, 'tzinfo') and lt.tzinfo is None:
                lt = lt.replace(tzinfo=timezone.utc)
            age_hours = (now - lt).total_seconds() / 3600
            if age_hours > max_hours:
                stale_types.append({
                    "table": table_name,
                    "last_updated_hours_ago": round(age_hours, 1),
                    "threshold_hours": max_hours,
                })

    data_quality = {
        "coherence_flags_24h": coherence_flags_24h,
        "unreviewed_flags": unreviewed_flags,
        "stale_data_types": stale_types,
    }

    # =========================================================================
    # 8. Storage
    # =========================================================================
    total_size_mb = round(total_bytes / 1_000_000, 1)
    growth_mb_day = sum(t["est_monthly_mb"] for t in tables.values()) / 30

    storage = {
        "estimated_total_mb": total_size_mb,
        "growth_mb_per_day": round(growth_mb_day, 2),
        "projected_monthly_mb": round(growth_mb_day * 30, 1),
        "total_rows": total_rows,
    }

    return {
        "generated_at": now.isoformat(),
        "tables": tables,
        "wallet_graph": wallet_graph,
        "entity_coverage": entity_coverage,
        "api_utilization": api_usage,
        "provenance": provenance,
        "temporal_depth": temporal,
        "data_quality": data_quality,
        "storage": storage,
    }
