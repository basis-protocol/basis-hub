-- Weekly divergence signal frequency from assessment events
SELECT
    DATE_TRUNC('week', created_at) as week_start,
    trigger_type,
    COUNT(*) as signal_count,
    COUNT(DISTINCT wallet_address) as wallets_affected,
    AVG(CASE WHEN severity = 'alert' THEN 1 WHEN severity = 'critical' THEN 2 ELSE 0 END) as avg_severity
FROM {{ ref('stg_assessment_events') }}
WHERE trigger_type IN ('score_change', 'concentration_shift', 'large_movement')
GROUP BY DATE_TRUNC('week', created_at), trigger_type
ORDER BY week_start DESC
