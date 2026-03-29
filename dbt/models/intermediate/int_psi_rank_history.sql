WITH daily_ranks AS (
    SELECT
        protocol_slug,
        protocol_name,
        scored_date,
        overall_score,
        RANK() OVER (PARTITION BY scored_date ORDER BY overall_score DESC) as daily_rank
    FROM {{ ref('stg_psi_scores') }}
    WHERE scored_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
    protocol_slug,
    MAX(protocol_name) as protocol_name,
    STDDEV_SAMP(daily_rank) as rank_volatility,
    AVG(daily_rank) as avg_rank,
    MAX(daily_rank) - MIN(daily_rank) as rank_range,
    COUNT(*) as days_observed
FROM daily_ranks
GROUP BY protocol_slug
