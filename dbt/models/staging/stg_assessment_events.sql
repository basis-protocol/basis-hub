SELECT
    id,
    wallet_address,
    trigger_type,
    severity,
    wallet_risk_score,
    wallet_risk_score_prev,
    concentration_hhi,
    total_stablecoin_value,
    content_hash,
    created_at,
    (created_at AT TIME ZONE 'UTC')::date as event_date
FROM {{ source('basis', 'assessment_events') }}
WHERE created_at >= NOW() - INTERVAL '30 days'
