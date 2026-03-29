-- Per-wallet score volatility over 7 days
SELECT
    wallet_address,
    STDDEV_SAMP(risk_score) as score_volatility,
    AVG(risk_score) as avg_score,
    COUNT(*) as observations,
    MAX(risk_score) - MIN(risk_score) as score_range
FROM {{ ref('stg_wallet_risk_scores') }}
WHERE scored_date >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY wallet_address
HAVING COUNT(*) >= 3
