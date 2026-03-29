-- Aggregate concentration (HHI) trend across all wallets
SELECT
    scored_date,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY concentration_hhi) as median_hhi,
    AVG(concentration_hhi) as mean_hhi,
    STDDEV_SAMP(concentration_hhi) as hhi_stddev,
    COUNT(*) as wallets_scored
FROM {{ ref('stg_wallet_risk_scores') }}
WHERE concentration_hhi IS NOT NULL
GROUP BY scored_date
ORDER BY scored_date
