SELECT
    assessment_id,
    wallet_address,
    holdings,
    stablecoin_scores,
    formula_version,
    inputs_hash,
    computed_at
FROM {{ source('basis', 'assessment_input_vectors') }}
WHERE computed_at >= NOW() - INTERVAL '7 days'
