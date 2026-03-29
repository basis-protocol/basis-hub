SELECT
    pulse_date,
    summary,
    created_at
FROM {{ source('basis', 'daily_pulses') }}
WHERE pulse_date >= CURRENT_DATE - INTERVAL '14 days'
ORDER BY pulse_date DESC
