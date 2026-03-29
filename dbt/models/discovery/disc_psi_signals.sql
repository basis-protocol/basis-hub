-- PSI domain signals
WITH rank_signals AS (
    SELECT
        'protocol_rank_instability' as signal_type,
        'psi' as domain,
        protocol_name || ' rank volatility: ' || ROUND(rank_volatility::numeric, 2) as title,
        'Protocol rank has been unstable over 7 days. Range: ' || rank_range || ' positions.' as description,
        jsonb_build_array(protocol_slug) as entities,
        CASE WHEN (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_psi_rank_history') }}) > 0
            THEN (rank_volatility - (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_psi_rank_history') }}))
                 / GREATEST((SELECT STDDEV_SAMP(rank_volatility) FROM {{ ref('int_psi_rank_history') }}), 0.01)
            ELSE 0 END as novelty_score,
        'shift' as direction,
        rank_volatility as magnitude,
        (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rank_volatility) FROM {{ ref('int_psi_rank_history') }}) as baseline,
        jsonb_build_object('avg_rank', avg_rank, 'rank_range', rank_range, 'days', days_observed) as detail
    FROM {{ ref('int_psi_rank_history') }}
    WHERE rank_volatility > 0
),
cluster_signals AS (
    SELECT
        'protocol_cluster_formation' as signal_type,
        'psi' as domain,
        proto_a || '-' || proto_b || ' correlation: ' || ROUND(correlation_7d::numeric, 2) as title,
        'High protocol score correlation detected over 7 days (' || data_points || ' data points). Potential cluster.' as description,
        jsonb_build_array(proto_a, proto_b) as entities,
        CASE WHEN correlation_7d > 0.8 THEN (correlation_7d - 0.5) * 5 ELSE 0 END as novelty_score,
        'cluster' as direction,
        correlation_7d as magnitude,
        0.5 as baseline,
        jsonb_build_object('data_points', data_points) as detail
    FROM {{ ref('int_psi_cluster_correlation') }}
    WHERE correlation_7d > 0.7
)

SELECT * FROM rank_signals
UNION ALL SELECT * FROM cluster_signals
