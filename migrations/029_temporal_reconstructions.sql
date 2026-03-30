-- Migration 029: Temporal reconstruction tables for historical score backfill
BEGIN;

CREATE TABLE IF NOT EXISTS temporal_reconstructions (
    id BIGSERIAL PRIMARY KEY,
    stablecoin_id VARCHAR(20) NOT NULL,
    target_date DATE NOT NULL,

    -- Reconstructed score
    overall_score DECIMAL(5,2),
    grade VARCHAR(2),
    peg_score DECIMAL(5,2),
    liquidity_score DECIMAL(5,2),
    mint_burn_score DECIMAL(5,2),
    distribution_score DECIMAL(5,2),
    structural_score DECIMAL(5,2),

    -- Provenance
    formula_version VARCHAR(20) NOT NULL,
    components_total INTEGER NOT NULL,
    components_available INTEGER NOT NULL,
    components_reconstructed INTEGER NOT NULL DEFAULT 0,
    components_carried INTEGER NOT NULL DEFAULT 0,
    components_missing INTEGER NOT NULL DEFAULT 0,
    coverage_pct DECIMAL(5,2),
    confidence VARCHAR(20) NOT NULL,

    -- Data source breakdown
    source_breakdown JSONB,
    component_detail JSONB,

    -- Metadata
    reconstructed_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(stablecoin_id, target_date, formula_version)
);

CREATE INDEX IF NOT EXISTS idx_tr_stablecoin_date ON temporal_reconstructions(stablecoin_id, target_date DESC);
CREATE INDEX IF NOT EXISTS idx_tr_confidence ON temporal_reconstructions(confidence);

INSERT INTO migrations (name) VALUES ('029_temporal_reconstructions') ON CONFLICT DO NOTHING;

COMMIT;
