-- Net flow by actor type per asset per day
-- Positive = net inflow, Negative = net outflow
WITH edge_flows AS (
    SELECT
        e.from_address,
        e.to_address,
        e.total_value_usd,
        e.last_transfer_at::date AS flow_date
    FROM {{ ref('stg_wallet_edges') }} e
    WHERE e.last_transfer_at > NOW() - INTERVAL '14 days'
),
wallet_assets AS (
    SELECT DISTINCT
        wh.wallet_address,
        wh.symbol,
        wh.token_address
    FROM wallet_graph.wallet_holdings wh
    WHERE wh.indexed_at > NOW() - INTERVAL '7 days'
      AND wh.value_usd >= 0.01
)
SELECT
    wa.symbol,
    wa.token_address,
    ef.flow_date,
    COALESCE(ac.actor_type, 'unknown') AS actor_type,
    SUM(CASE
        WHEN ef.to_address = wa.wallet_address THEN ef.total_value_usd
        WHEN ef.from_address = wa.wallet_address THEN -ef.total_value_usd
        ELSE 0
    END) AS net_flow_usd,
    COUNT(DISTINCT wa.wallet_address) AS wallets_involved
FROM edge_flows ef
JOIN wallet_assets wa
    ON wa.wallet_address IN (ef.from_address, ef.to_address)
LEFT JOIN {{ ref('stg_actor_classifications') }} ac
    ON ac.wallet_address = wa.wallet_address
GROUP BY wa.symbol, wa.token_address, ef.flow_date, COALESCE(ac.actor_type, 'unknown')
ORDER BY ef.flow_date, wa.symbol, actor_type
