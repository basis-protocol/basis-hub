-- Pairwise protocol score correlation to detect cluster formation
WITH pivoted AS (
    SELECT
        a.scored_date,
        a.protocol_slug as proto_a,
        b.protocol_slug as proto_b,
        a.overall_score as score_a,
        b.overall_score as score_b
    FROM {{ ref('stg_psi_scores') }} a
    JOIN {{ ref('stg_psi_scores') }} b
        ON a.scored_date = b.scored_date
        AND a.protocol_slug < b.protocol_slug
    WHERE a.scored_date >= CURRENT_DATE - INTERVAL '7 days'
)
SELECT
    proto_a,
    proto_b,
    CORR(score_a, score_b) as correlation_7d,
    COUNT(*) as data_points
FROM pivoted
GROUP BY proto_a, proto_b
HAVING COUNT(*) >= 5
