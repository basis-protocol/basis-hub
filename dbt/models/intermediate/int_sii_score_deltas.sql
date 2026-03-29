-- Score velocity and acceleration per stablecoin
WITH ordered AS (
    SELECT
        stablecoin,
        score_date,
        overall_score,
        LAG(overall_score) OVER (PARTITION BY stablecoin ORDER BY score_date) as prev_score,
        LAG(overall_score, 2) OVER (PARTITION BY stablecoin ORDER BY score_date) as prev_prev_score
    FROM {{ ref('stg_score_history') }}
    WHERE score_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
    stablecoin,
    score_date,
    overall_score,
    overall_score - COALESCE(prev_score, overall_score) as velocity,
    (overall_score - COALESCE(prev_score, overall_score))
        - (COALESCE(prev_score, overall_score) - COALESCE(prev_prev_score, prev_score, overall_score)) as acceleration
FROM ordered
WHERE prev_score IS NOT NULL
