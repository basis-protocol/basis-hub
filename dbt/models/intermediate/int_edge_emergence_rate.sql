-- Daily edge creation rate
SELECT
    (created_at AT TIME ZONE 'UTC')::date as edge_date,
    COUNT(*) as edges_created,
    SUM(total_value_usd) as total_value,
    AVG(weight) as avg_weight
FROM {{ source('wallet_graph', 'wallet_edges') }}
WHERE created_at >= NOW() - INTERVAL '14 days'
GROUP BY (created_at AT TIME ZONE 'UTC')::date
ORDER BY edge_date
