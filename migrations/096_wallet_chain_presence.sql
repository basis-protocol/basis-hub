-- Migration 096: Wallet Chain Presence (Phase 2 Sprint 2)
-- Cross-chain resolution for wallet_graph addresses

CREATE TABLE IF NOT EXISTS wallet_chain_presence (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    chain_id INTEGER NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tx_count BIGINT,
    native_balance_wei NUMERIC(78,0),
    native_balance_usd NUMERIC,
    token_count INTEGER,
    discovery_method TEXT NOT NULL,
    discovery_entity TEXT,
    UNIQUE(wallet_address, chain)
);

CREATE INDEX IF NOT EXISTS idx_wcp_chain ON wallet_chain_presence(chain);
CREATE INDEX IF NOT EXISTS idx_wcp_wallet ON wallet_chain_presence(wallet_address);
CREATE INDEX IF NOT EXISTS idx_wcp_verified ON wallet_chain_presence(last_verified_at DESC);

INSERT INTO migrations (name) VALUES ('096_wallet_chain_presence') ON CONFLICT DO NOTHING;
