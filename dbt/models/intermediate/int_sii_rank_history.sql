-- Daily rank for each stablecoin + rank volatility over 7 days
WITH daily_ranks AS (
    SELECT
        stablecoin,
        score_date,
        overall_score,
        RANK() OVER (PARTITION BY score_date ORDER BY overall_score DESC) as daily_rank
    FROM {{ ref('stg_score_history') }}
    WHERE score_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
    stablecoin,
    STDDEV_SAMP(daily_rank) as rank_volatility,
    AVG(daily_rank) as avg_rank,
    MIN(daily_rank) as best_rank,
    MAX(daily_rank) as worst_rank,
    MAX(daily_rank) - MIN(daily_rank) as rank_range,
    COUNT(*) as days_observed,
    MAX(score_date) as latest_date
FROM daily_ranks
GROUP BY stablecoin
