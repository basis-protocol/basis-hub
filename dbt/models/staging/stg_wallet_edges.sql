SELECT
    from_address,
    to_address,
    transfer_count,
    total_value_usd,
    first_transfer_at,
    last_transfer_at,
    weight,
    tokens_transferred
FROM {{ source('wallet_graph', 'wallet_edges') }}
WHERE weight > 0.1
  AND last_transfer_at >= NOW() - INTERVAL '30 days'
