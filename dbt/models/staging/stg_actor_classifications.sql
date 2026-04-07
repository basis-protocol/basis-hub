SELECT
    wallet_address,
    actor_type,
    agent_probability,
    confidence,
    tx_count_basis,
    methodology_version,
    classified_at,
    updated_at
FROM {{ source('wallet_graph', 'actor_classifications') }}
