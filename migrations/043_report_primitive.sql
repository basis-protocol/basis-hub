-- Migration 043: Report primitive tables
-- Batch hashes, CQI attestations, report attestations

-- Batch hash per scoring cycle (floor of attestation chain)
CREATE TABLE IF NOT EXISTS component_batch_hashes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    batch_hash VARCHAR(64) NOT NULL,
    component_count INTEGER NOT NULL,
    methodology_version VARCHAR(20) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(entity_type, entity_id, computed_at)
);

-- CQI composition attestation
CREATE TABLE IF NOT EXISTS cqi_attestations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sii_symbol VARCHAR(20) NOT NULL,
    psi_slug VARCHAR(50) NOT NULL,
    sii_score NUMERIC(6,2),
    psi_score NUMERIC(6,2),
    cqi_score NUMERIC(6,2),
    sii_hash VARCHAR(64),
    psi_hash VARCHAR(64),
    composition_method VARCHAR(20) DEFAULT 'geometric_mean',
    methodology_version VARCHAR(20) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Report attestation
CREATE TABLE IF NOT EXISTS report_attestations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(20) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    template VARCHAR(30) NOT NULL,
    lens VARCHAR(10),
    lens_version VARCHAR(10),
    report_hash VARCHAR(64) NOT NULL UNIQUE,
    score_hashes JSONB NOT NULL,
    cqi_hashes JSONB,
    methodology_version VARCHAR(20) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_attestations_entity ON report_attestations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_report_attestations_hash ON report_attestations(report_hash);
CREATE INDEX IF NOT EXISTS idx_component_batch_hashes_entity ON component_batch_hashes(entity_type, entity_id);

INSERT INTO migrations (name) VALUES ('043_report_primitive') ON CONFLICT DO NOTHING;
