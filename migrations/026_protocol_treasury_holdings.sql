-- Migration 026: Protocol treasury token-level holdings with SII cross-reference
-- Stores per-token breakdown from DeFiLlama treasury endpoint

CREATE TABLE IF NOT EXISTS protocol_treasury_holdings (
    id BIGSERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    token_name VARCHAR(200) NOT NULL,
    token_symbol VARCHAR(50),
    chain VARCHAR(100),
    usd_value DOUBLE PRECISION NOT NULL,
    is_stablecoin BOOLEAN DEFAULT FALSE,
    sii_score DOUBLE PRECISION,  -- NULL if not SII-scored
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_treasury_holdings_unique
ON protocol_treasury_holdings(protocol_slug, token_symbol, chain, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_treasury_stablecoins
ON protocol_treasury_holdings(is_stablecoin, protocol_slug)
WHERE is_stablecoin = TRUE;
