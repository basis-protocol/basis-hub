-- Track how much each wallet's input vector changes between scoring cycles
WITH ordered AS (
    SELECT
        wallet_address,
        holdings,
        stablecoin_scores,
        inputs_hash,
        computed_at,
        LAG(inputs_hash) OVER (PARTITION BY wallet_address ORDER BY computed_at) as prev_hash,
        LAG(holdings) OVER (PARTITION BY wallet_address ORDER BY computed_at) as prev_holdings
    FROM {{ ref('stg_input_vectors') }}
)
SELECT
    wallet_address,
    computed_at,
    inputs_hash,
    prev_hash,
    CASE WHEN inputs_hash = prev_hash THEN 1.0 ELSE 0.0 END as exact_match,
    CASE WHEN prev_hash IS NULL THEN 'first_observation'
         WHEN inputs_hash = prev_hash THEN 'unchanged'
         ELSE 'changed' END as change_status
FROM ordered
WHERE prev_hash IS NOT NULL
