-- Extract key metrics from pulse JSON and compute deltas
SELECT
    pulse_date,
    (summary->>'methodology_version') as methodology_version,
    (summary->'network_state'->>'wallets_scored')::int as wallets_scored,
    (summary->'network_state'->>'wallets_indexed')::int as wallets_indexed,
    (summary->'network_state'->>'total_tracked_usd')::numeric as total_tracked_usd,
    (summary->'network_state'->>'stablecoins_scored')::int as stablecoins_scored,
    (summary->'network_state'->>'protocols_scored')::int as protocols_scored,
    (summary->'events_24h'->>'total')::int as events_total,
    (summary->'events_24h'->>'alert')::int as events_alert,
    (summary->'events_24h'->>'critical')::int as events_critical,
    LAG((summary->'network_state'->>'wallets_scored')::int) OVER (ORDER BY pulse_date) as prev_wallets_scored,
    LAG((summary->'events_24h'->>'total')::int) OVER (ORDER BY pulse_date) as prev_events_total
FROM {{ ref('stg_daily_pulses') }}
ORDER BY pulse_date
