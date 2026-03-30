-- Migration 029: Protocol backlog for automated discovery, enrichment, and promotion
-- Mirrors the stablecoin backlog pattern (wallet_graph.unscored_assets) but for protocols

CREATE TABLE IF NOT EXISTS protocol_backlog (
    slug VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200),
    category VARCHAR(100),
    tvl_usd DOUBLE PRECISION DEFAULT 0,
    gecko_id VARCHAR(100),
    snapshot_space VARCHAR(200),
    main_contract VARCHAR(100),

    -- Demand signals
    stablecoin_exposure_usd DOUBLE PRECISION DEFAULT 0,
    unscored_stablecoin_exposure_usd DOUBLE PRECISION DEFAULT 0,
    unscored_stablecoins TEXT[],

    -- Enrichment tracking
    components_available INTEGER DEFAULT 0,
    components_total INTEGER DEFAULT 24,
    coverage_pct DOUBLE PRECISION DEFAULT 0,
    enrichment_status VARCHAR(20) DEFAULT 'discovered',
    last_enrichment_at TIMESTAMPTZ,

    -- Metadata
    scoring_priority INTEGER,
    notes TEXT,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_protocol_backlog_status ON protocol_backlog(enrichment_status);
CREATE INDEX IF NOT EXISTS idx_protocol_backlog_priority ON protocol_backlog(stablecoin_exposure_usd DESC);
