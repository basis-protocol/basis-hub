-- Migration 053: Audit fixes — divergence storage + integrity persistence
-- Fixes audit items #2 and #9.

-- ============================================================================
-- Divergence Signals table (Audit Fix #2)
-- ============================================================================

CREATE TABLE IF NOT EXISTS divergence_signals (
    id SERIAL PRIMARY KEY,
    detector_name TEXT NOT NULL,       -- e.g. 'asset_quality', 'wallet_concentration', 'quality_flow'
    entity_type TEXT,                  -- 'stablecoin', 'protocol', 'pair'
    entity_id TEXT,                    -- symbol or slug
    signal_direction TEXT,             -- 'deteriorating', 'improving', 'anomalous'
    magnitude FLOAT,                   -- normalized strength
    severity TEXT,                     -- 'critical', 'alert', 'notable'
    detail JSONB,                      -- full detector output
    cycle_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_divergence_signals_entity ON divergence_signals (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_divergence_signals_time ON divergence_signals (cycle_timestamp);
CREATE INDEX IF NOT EXISTS idx_divergence_signals_severity ON divergence_signals (severity);

-- ============================================================================
-- Integrity Checks table (Audit Fix #9)
-- ============================================================================

CREATE TABLE IF NOT EXISTS integrity_checks (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,               -- 'sii', 'psi', 'wallets', 'cda', 'events', 'edges', 'pulse'
    check_type TEXT NOT NULL,           -- 'freshness', 'coherence'
    status TEXT NOT NULL,               -- 'pass', 'warn', 'fail'
    detail JSONB,                       -- full check output
    cycle_timestamp TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_integrity_domain_time ON integrity_checks (domain, cycle_timestamp);
CREATE INDEX IF NOT EXISTS idx_integrity_status ON integrity_checks (status);
