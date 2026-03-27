"""
Verification Agent — Configuration
====================================
Thresholds, intervals, and toggle flags for the agent and publisher.
"""

AGENT_CONFIG = {
    # Watcher
    "watch_interval_minutes": 15,
    "daily_cycle_utc_hour": 0,       # 00:00 UTC, after SII scoring
    "daily_pulse_utc_hour": 7,       # 07:00 UTC, social post time

    # Trigger thresholds
    "movement_threshold_usd": 1_000_000,
    "score_change_threshold_pts": 3.0,
    "concentration_shift_from_pct": 20.0,
    "concentration_shift_to_pct": 40.0,
    "concentration_min_wallet_value": 500_000,
    "depeg_threshold_pct": 1.0,
    "depeg_duration_minutes": 60,

    # Classifier
    "divergence_sii_ceiling": 80,     # only flag divergence below this SII
    "alert_score_delta_pts": 3.0,
    "critical_score_delta_pts": 5.0,
    "critical_depeg_pct": 1.0,

    # Publisher
    "pages_enabled": True,
    "social_enabled": False,          # OFF by default until accounts set up
    "onchain_enabled": False,         # OFF until oracle keys funded
    "pulse_enabled": True,

    # Limits
    "max_assessments_per_cycle": 500, # prevent runaway on first run
    "max_broadcasts_per_day": 10,     # prevent spam
}
