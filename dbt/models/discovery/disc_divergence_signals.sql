-- Divergence domain signals — assessment event frequency anomalies
WITH weekly_signals AS (
    SELECT
        'divergence_frequency_shift' as signal_type,
        'divergence' as domain,
        trigger_type || ': ' || signal_count || ' signals this week (' || wallets_affected || ' wallets)' as title,
        'Weekly ' || trigger_type || ' frequency: ' || signal_count || ' events affecting ' || wallets_affected || ' wallets. Avg severity: ' || ROUND(avg_severity::numeric, 2) as description,
        jsonb_build_array(trigger_type) as entities,
        -- Novelty: compare this week vs overall average
        CASE WHEN (SELECT AVG(signal_count) FROM {{ ref('int_divergence_frequency') }} WHERE trigger_type = df.trigger_type) > 0
             THEN (signal_count - (SELECT AVG(signal_count) FROM {{ ref('int_divergence_frequency') }} WHERE trigger_type = df.trigger_type))
                  / GREATEST((SELECT STDDEV_SAMP(signal_count) FROM {{ ref('int_divergence_frequency') }} WHERE trigger_type = df.trigger_type), 1)
             ELSE 0 END as novelty_score,
        CASE WHEN signal_count > (SELECT AVG(signal_count) FROM {{ ref('int_divergence_frequency') }} WHERE trigger_type = df.trigger_type) THEN 'up' ELSE 'down' END as direction,
        signal_count::float as magnitude,
        (SELECT AVG(signal_count) FROM {{ ref('int_divergence_frequency') }} WHERE trigger_type = df.trigger_type) as baseline,
        jsonb_build_object('wallets_affected', wallets_affected, 'avg_severity', avg_severity) as detail
    FROM {{ ref('int_divergence_frequency') }} df
    WHERE week_start = (SELECT MAX(week_start) FROM {{ ref('int_divergence_frequency') }})
),
severity_signals AS (
    SELECT
        'high_severity_week' as signal_type,
        'divergence' as domain,
        'High severity events: avg ' || ROUND(avg_severity::numeric, 2) || ' for ' || trigger_type as title,
        'Severity escalation detected for ' || trigger_type || ' events this week.' as description,
        jsonb_build_array(trigger_type) as entities,
        (avg_severity - 0.5) * 3 as novelty_score,
        'up' as direction,
        avg_severity as magnitude,
        0.5 as baseline,
        jsonb_build_object('signal_count', signal_count, 'wallets_affected', wallets_affected) as detail
    FROM {{ ref('int_divergence_frequency') }}
    WHERE week_start = (SELECT MAX(week_start) FROM {{ ref('int_divergence_frequency') }})
      AND avg_severity > 1.0
)

SELECT * FROM weekly_signals
UNION ALL SELECT * FROM severity_signals
