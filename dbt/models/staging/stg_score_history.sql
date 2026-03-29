SELECT
    stablecoin,
    score_date,
    overall_score,
    grade,
    peg_score,
    liquidity_score,
    mint_burn_score,
    distribution_score,
    structural_score,
    daily_change,
    weekly_change
FROM {{ source('basis', 'score_history') }}
WHERE score_date >= CURRENT_DATE - INTERVAL '30 days'
