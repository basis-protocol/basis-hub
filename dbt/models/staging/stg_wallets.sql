SELECT
    address,
    first_seen_at,
    last_scored_at,
    scoring_enabled
FROM {{ source('wallet_graph', 'wallets') }}
