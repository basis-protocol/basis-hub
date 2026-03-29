-- Daily distribution shape of all SII scores
WITH daily AS (
    SELECT
        score_date,
        MAX(overall_score) - MIN(overall_score) as spread,
        STDDEV_SAMP(overall_score) as std_dev,
        AVG(overall_score) as mean_score,
        COUNT(*) as coins_scored
    FROM {{ ref('stg_score_history') }}
    WHERE score_date >= CURRENT_DATE - INTERVAL '14 days'
    GROUP BY score_date
)
SELECT
    *,
    AVG(spread) OVER (ORDER BY score_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as spread_7d_avg,
    STDDEV_SAMP(spread) OVER (ORDER BY score_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as spread_7d_stddev
FROM daily
