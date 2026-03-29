-- Grade migration matrix: how wallets move between risk grades over time
WITH current_grades AS (
    SELECT DISTINCT ON (wallet_address)
        wallet_address,
        risk_grade as current_grade,
        risk_score as current_score,
        scored_date
    FROM {{ ref('stg_wallet_risk_scores') }}
    WHERE scored_date >= CURRENT_DATE - INTERVAL '2 days'
    ORDER BY wallet_address, scored_date DESC
),
prior_grades AS (
    SELECT DISTINCT ON (wallet_address)
        wallet_address,
        risk_grade as prior_grade,
        risk_score as prior_score,
        scored_date
    FROM {{ ref('stg_wallet_risk_scores') }}
    WHERE scored_date BETWEEN CURRENT_DATE - INTERVAL '9 days' AND CURRENT_DATE - INTERVAL '5 days'
    ORDER BY wallet_address, scored_date DESC
)
SELECT
    p.prior_grade,
    c.current_grade,
    COUNT(*) as wallet_count,
    AVG(c.current_score - p.prior_score) as avg_score_change,
    CASE WHEN p.prior_grade = c.current_grade THEN 'stable'
         WHEN c.current_score > p.prior_score THEN 'upgraded'
         ELSE 'downgraded' END as migration_direction
FROM current_grades c
JOIN prior_grades p ON c.wallet_address = p.wallet_address
GROUP BY p.prior_grade, c.current_grade
ORDER BY p.prior_grade, c.current_grade
