-- Migration 035: Governance snapshots, market tracking, and collateral coverage
-- Supports Prompt 1 (governance change detection), Prompt 2 (collateral coverage),
-- and Prompt 3 (market listing velocity)

-- Table 1: PSI governance config snapshots
CREATE TABLE IF NOT EXISTS psi_governance_snapshots (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    chain VARCHAR(50),
    snapshot_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    config_hash VARCHAR(64) NOT NULL,
    raw_config JSONB NOT NULL,
    upgrade_authority VARCHAR(128),
    multisig_threshold VARCHAR(32),
    timelock_seconds INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (protocol_slug, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_gov_snapshots_slug ON psi_governance_snapshots(protocol_slug, snapshot_date DESC);

-- Table 2: Protocol market snapshots (for market listing velocity)
CREATE TABLE IF NOT EXISTS protocol_market_snapshots (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    market_count INTEGER NOT NULL DEFAULT 0,
    market_list JSONB,
    new_markets JSONB,
    removed_markets JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (protocol_slug, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_market_snapshots_slug ON protocol_market_snapshots(protocol_slug, snapshot_date DESC);
