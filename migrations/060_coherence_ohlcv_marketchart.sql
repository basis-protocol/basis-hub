-- Migration 060: Coherence violations + OHLCV + market chart history

-- =============================================================================
-- Coherence violations — proper per-record tracking
-- =============================================================================
-- The old coherence_reports table was for daily sweep summaries.
-- This table stores individual data coherence violations with per-record granularity.

CREATE TABLE IF NOT EXISTS coherence_violations (
    id BIGSERIAL PRIMARY KEY,
    data_type TEXT NOT NULL,           -- liquidity_depth, exchange_snapshots, etc.
    entity_id TEXT NOT NULL,
    field_name TEXT,
    violation_type TEXT NOT NULL,       -- extreme_drop, zero_replacement, negative_value, etc.
    severity TEXT NOT NULL DEFAULT 'warning',  -- warning, critical
    previous_value NUMERIC,
    incoming_value NUMERIC,
    details TEXT,
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    review_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_coherence_viol_type
    ON coherence_violations(data_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coherence_viol_entity
    ON coherence_violations(entity_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_coherence_viol_unreviewed
    ON coherence_violations(reviewed, created_at DESC) WHERE reviewed = FALSE;
CREATE INDEX IF NOT EXISTS idx_coherence_viol_severity
    ON coherence_violations(severity, created_at DESC);

-- =============================================================================
-- GeckoTerminal OHLCV — pool-level candlestick data
-- =============================================================================

CREATE TABLE IF NOT EXISTS dex_pool_ohlcv (
    id BIGSERIAL PRIMARY KEY,
    pool_address TEXT NOT NULL,
    chain TEXT NOT NULL,
    dex TEXT,                          -- uniswap_v3, curve, etc.
    asset_id TEXT,                     -- stablecoin ID for joining
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume NUMERIC,
    trades_count INTEGER,
    raw_data JSONB,
    provenance_proof_id INTEGER REFERENCES provenance_proofs(id),
    UNIQUE(pool_address, chain, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_pool_time
    ON dex_pool_ohlcv(pool_address, chain, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ohlcv_asset
    ON dex_pool_ohlcv(asset_id, timestamp DESC);

-- =============================================================================
-- Market chart history — custom date range backfill
-- =============================================================================

CREATE TABLE IF NOT EXISTS market_chart_history (
    id BIGSERIAL PRIMARY KEY,
    coin_id TEXT NOT NULL,             -- coingecko_id
    stablecoin_id TEXT,                -- internal ID for joining
    timestamp TIMESTAMPTZ NOT NULL,
    price NUMERIC,
    market_cap NUMERIC,
    total_volume NUMERIC,
    granularity TEXT NOT NULL,          -- 5min, hourly, daily
    provenance_proof_id INTEGER REFERENCES provenance_proofs(id),
    UNIQUE(coin_id, timestamp, granularity)
);

CREATE INDEX IF NOT EXISTS idx_mch_coin_time
    ON market_chart_history(coin_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_mch_stablecoin
    ON market_chart_history(stablecoin_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_mch_granularity
    ON market_chart_history(granularity, timestamp DESC);

INSERT INTO migrations (name) VALUES ('060_coherence_ohlcv_marketchart') ON CONFLICT DO NOTHING;
