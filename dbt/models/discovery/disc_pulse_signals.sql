-- Pulse domain signals — network state changes
WITH wallet_growth_signals AS (
    SELECT
        'wallet_growth_spike' as signal_type,
        'pulse' as domain,
        'Wallets scored: ' || wallets_scored || ' (prev: ' || COALESCE(prev_wallets_scored::text, 'N/A') || ')' as title,
        'Daily wallet scoring count changed significantly.' as description,
        '[]'::jsonb as entities,
        CASE WHEN prev_wallets_scored > 0
             THEN ABS(wallets_scored - prev_wallets_scored)::float / prev_wallets_scored * 10
             ELSE 0 END as novelty_score,
        CASE WHEN wallets_scored > COALESCE(prev_wallets_scored, 0) THEN 'up' ELSE 'down' END as direction,
        wallets_scored::float as magnitude,
        COALESCE(prev_wallets_scored, 0)::float as baseline,
        jsonb_build_object(
            'wallets_indexed', wallets_indexed,
            'total_tracked_usd', total_tracked_usd,
            'stablecoins_scored', stablecoins_scored,
            'protocols_scored', protocols_scored
        ) as detail
    FROM {{ ref('int_pulse_deltas') }}
    WHERE pulse_date = (SELECT MAX(pulse_date) FROM {{ ref('int_pulse_deltas') }})
      AND prev_wallets_scored IS NOT NULL
      AND ABS(wallets_scored - prev_wallets_scored) > 5
),
event_spike_signals AS (
    SELECT
        'event_spike' as signal_type,
        'pulse' as domain,
        'Events: ' || events_total || ' (prev: ' || COALESCE(prev_events_total::text, 'N/A') || ')' as title,
        'Daily event count changed. Alerts: ' || COALESCE(events_alert, 0) || ', Critical: ' || COALESCE(events_critical, 0) as description,
        '[]'::jsonb as entities,
        CASE WHEN prev_events_total > 0
             THEN ABS(events_total - prev_events_total)::float / prev_events_total * 5
             ELSE 0 END as novelty_score,
        CASE WHEN events_total > COALESCE(prev_events_total, 0) THEN 'up' ELSE 'down' END as direction,
        events_total::float as magnitude,
        COALESCE(prev_events_total, 0)::float as baseline,
        jsonb_build_object('events_alert', events_alert, 'events_critical', events_critical) as detail
    FROM {{ ref('int_pulse_deltas') }}
    WHERE pulse_date = (SELECT MAX(pulse_date) FROM {{ ref('int_pulse_deltas') }})
      AND prev_events_total IS NOT NULL
      AND ABS(events_total - prev_events_total) > 3
)

SELECT * FROM wallet_growth_signals
UNION ALL SELECT * FROM event_spike_signals
