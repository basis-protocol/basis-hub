-- Actor composition per stablecoin: what % of USD value is held by each actor type?
-- Joined with wallet_holdings to get per-asset breakdown.
WITH holdings AS (
    SELECT
        wh.token_address,
        wh.symbol,
        wh.wallet_address,
        wh.value_usd,
        public.immutable_date(wh.indexed_at) AS indexed_date
    FROM wallet_graph.wallet_holdings wh
    WHERE wh.indexed_at > NOW() - INTERVAL '30 days'
      AND wh.value_usd >= 0.01
),
classified AS (
    SELECT
        h.token_address,
        h.symbol,
        h.indexed_date,
        COALESCE(ac.actor_type, 'unknown') AS actor_type,
        SUM(h.value_usd) AS total_usd,
        COUNT(DISTINCT h.wallet_address) AS wallet_count
    FROM holdings h
    LEFT JOIN {{ ref('stg_actor_classifications') }} ac
        ON ac.wallet_address = h.wallet_address
    GROUP BY h.token_address, h.symbol, h.indexed_date, COALESCE(ac.actor_type, 'unknown')
)
SELECT
    token_address,
    symbol,
    indexed_date,
    actor_type,
    total_usd,
    wallet_count,
    total_usd / NULLIF(SUM(total_usd) OVER (PARTITION BY token_address, indexed_date), 0) * 100 AS pct_value
FROM classified
ORDER BY indexed_date, token_address, actor_type
