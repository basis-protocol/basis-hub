SELECT
    protocol_slug,
    protocol_name,
    overall_score,
    grade,
    category_scores,
    scored_date,
    computed_at
FROM {{ source('basis', 'psi_scores') }}
WHERE scored_date >= CURRENT_DATE - INTERVAL '30 days'
