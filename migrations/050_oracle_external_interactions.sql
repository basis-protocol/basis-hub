-- 050: Oracle external interactions tracking
-- Stores non-keeper transactions to oracle and SBT contracts on Base/Arbitrum.

CREATE TABLE IF NOT EXISTS oracle_external_interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain VARCHAR(20) NOT NULL,
    contract_type VARCHAR(20) NOT NULL,
    tx_hash VARCHAR(66) NOT NULL UNIQUE,
    from_address VARCHAR(42) NOT NULL,
    function_selector VARCHAR(10),
    block_number BIGINT,
    block_timestamp TIMESTAMPTZ,
    gas_used BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oracle_ext_chain
    ON oracle_external_interactions(chain, block_timestamp DESC);
