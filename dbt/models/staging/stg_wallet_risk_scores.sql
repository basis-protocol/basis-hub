SELECT
    wallet_address,
    risk_score,
    risk_grade,
    concentration_hhi,
    concentration_grade,
    unscored_pct,
    num_scored_holdings,
    total_stablecoin_value,
    size_tier,
    computed_at,
    (computed_at AT TIME ZONE 'UTC')::date as scored_date
FROM {{ source('wallet_graph', 'wallet_risk_scores') }}
WHERE computed_at >= NOW() - INTERVAL '30 days'
