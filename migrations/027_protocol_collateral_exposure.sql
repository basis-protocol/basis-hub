-- Migration 027: Protocol collateral/pool stablecoin exposure
-- Tracks what stablecoins each protocol accepts as collateral or liquidity,
-- sourced from DeFiLlama yields/pools endpoint.

CREATE TABLE IF NOT EXISTS protocol_collateral_exposure (
    id BIGSERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    pool_id VARCHAR(200),
    token_symbol VARCHAR(50) NOT NULL,
    chain VARCHAR(100),
    tvl_usd DOUBLE PRECISION NOT NULL,
    is_stablecoin BOOLEAN DEFAULT FALSE,
    is_sii_scored BOOLEAN DEFAULT FALSE,
    sii_score DOUBLE PRECISION,
    pool_type VARCHAR(50),         -- 'lending', 'dex', 'staking', 'yield'
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_collateral_exposure_unique
ON protocol_collateral_exposure(protocol_slug, pool_id, snapshot_date);

CREATE INDEX IF NOT EXISTS idx_collateral_stablecoins
ON protocol_collateral_exposure(is_stablecoin, protocol_slug)
WHERE is_stablecoin = TRUE;

CREATE INDEX IF NOT EXISTS idx_collateral_unscored
ON protocol_collateral_exposure(is_stablecoin, is_sii_scored)
WHERE is_stablecoin = TRUE AND is_sii_scored = FALSE;
