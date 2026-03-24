-- Migration 010: CDA Monitor Watches
-- Stores Parallel Monitor watch IDs for proactive alerting.

ALTER TABLE cda_issuer_registry ADD COLUMN IF NOT EXISTS parallel_monitor_id VARCHAR(100);

CREATE TABLE IF NOT EXISTS cda_monitors (
    id SERIAL PRIMARY KEY,
    asset_symbol VARCHAR(20) NOT NULL,
    parallel_monitor_id VARCHAR(100) UNIQUE,
    query TEXT NOT NULL,
    url TEXT,
    frequency VARCHAR(20) DEFAULT 'daily',
    is_active BOOLEAN DEFAULT TRUE,
    last_alert_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cda_monitors_symbol ON cda_monitors(asset_symbol);
CREATE INDEX IF NOT EXISTS idx_cda_monitors_pid ON cda_monitors(parallel_monitor_id);
