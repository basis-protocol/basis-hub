-- Pairwise score trajectories for correlation computation
WITH pivoted AS (
    SELECT
        a.score_date,
        a.overall_score as score_a,
        b.overall_score as score_b,
        a.stablecoin as coin_a,
        b.stablecoin as coin_b
    FROM {{ ref('stg_score_history') }} a
    JOIN {{ ref('stg_score_history') }} b
        ON a.score_date = b.score_date
        AND a.stablecoin < b.stablecoin
    WHERE a.score_date >= CURRENT_DATE - INTERVAL '14 days'
)
SELECT
    coin_a,
    coin_b,
    CORR(score_a, score_b) as correlation_14d,
    COUNT(*) as data_points
FROM pivoted
GROUP BY coin_a, coin_b
HAVING COUNT(*) >= 7
