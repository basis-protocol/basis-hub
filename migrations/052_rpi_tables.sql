-- Migration 052: Risk Posture Index (RPI) tables
-- RPI measures how well a protocol manages risk (governance spending,
-- parameter changes, vendor relationships, incident history).

BEGIN;

-- Core RPI component readings — per-protocol, per-component
CREATE TABLE IF NOT EXISTS rpi_components (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    component_id VARCHAR(80) NOT NULL,
    component_type VARCHAR(10) NOT NULL DEFAULT 'base',  -- 'base' or 'lens'
    lens_id VARCHAR(60),  -- NULL for base components, lens name for lens components
    raw_value DOUBLE PRECISION,
    normalized_score DOUBLE PRECISION,
    source_type VARCHAR(20) NOT NULL DEFAULT 'automated',  -- 'automated', 'seed', 'manual'
    data_source VARCHAR(100),
    metadata JSONB,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rpi_components_slug
    ON rpi_components(protocol_slug, component_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_rpi_components_type
    ON rpi_components(component_type, lens_id);

-- Computed RPI scores — base scores only (lensed scores are computed on-the-fly)
CREATE TABLE IF NOT EXISTS rpi_scores (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    protocol_name VARCHAR(200),
    overall_score DOUBLE PRECISION,
    grade VARCHAR(3),
    component_scores JSONB,
    raw_values JSONB,
    inputs_hash VARCHAR(66),
    methodology_version VARCHAR(20) DEFAULT 'rpi-v2.0.0',
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    scored_date DATE DEFAULT CURRENT_DATE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rpi_scores_unique_per_day
    ON rpi_scores(protocol_slug, scored_date);

ALTER TABLE rpi_scores ADD CONSTRAINT rpi_scores_protocol_slug_scored_date_key
    UNIQUE USING INDEX idx_rpi_scores_unique_per_day;

-- Governance proposals scraped from Snapshot and Tally
CREATE TABLE IF NOT EXISTS governance_proposals (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    proposal_id VARCHAR(200) NOT NULL,
    source VARCHAR(20) NOT NULL,  -- 'snapshot' or 'tally'
    title TEXT,
    body_excerpt TEXT,  -- first 500 chars for classification
    is_risk_related BOOLEAN DEFAULT FALSE,
    risk_keywords TEXT[],
    budget_amount_usd DOUBLE PRECISION,
    vote_for DOUBLE PRECISION,
    vote_against DOUBLE PRECISION,
    vote_abstain DOUBLE PRECISION,
    quorum_reached BOOLEAN,
    participation_rate DOUBLE PRECISION,
    proposal_state VARCHAR(30),  -- 'active', 'closed', 'executed', etc.
    created_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    scraped_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gov_proposals_unique
    ON governance_proposals(protocol_slug, proposal_id, source);
CREATE INDEX IF NOT EXISTS idx_gov_proposals_slug_date
    ON governance_proposals(protocol_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_gov_proposals_risk
    ON governance_proposals(protocol_slug, is_risk_related) WHERE is_risk_related = TRUE;

-- On-chain parameter change events
CREATE TABLE IF NOT EXISTS parameter_changes (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    tx_hash VARCHAR(66) NOT NULL,
    block_number BIGINT,
    parameter_type VARCHAR(100),
    function_signature VARCHAR(200),
    old_value TEXT,
    new_value TEXT,
    contract_address VARCHAR(42),
    chain VARCHAR(30) DEFAULT 'ethereum',
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_param_changes_tx
    ON parameter_changes(protocol_slug, tx_hash);
CREATE INDEX IF NOT EXISTS idx_param_changes_slug_date
    ON parameter_changes(protocol_slug, detected_at DESC);

-- Curated risk incidents
CREATE TABLE IF NOT EXISTS risk_incidents (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    incident_date DATE NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT,
    severity VARCHAR(20) NOT NULL,  -- 'critical', 'major', 'moderate', 'minor'
    funds_at_risk_usd DOUBLE PRECISION,
    funds_recovered_usd DOUBLE PRECISION,
    reviewed BOOLEAN DEFAULT FALSE,
    source_url TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_risk_incidents_slug
    ON risk_incidents(protocol_slug, incident_date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_incidents_reviewed
    ON risk_incidents(protocol_slug, reviewed) WHERE reviewed = TRUE;

-- RPI score history for time-series queries
CREATE TABLE IF NOT EXISTS rpi_score_history (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    score_date DATE NOT NULL DEFAULT CURRENT_DATE,
    overall_score DOUBLE PRECISION,
    component_scores JSONB,
    methodology_version VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rpi_history_unique
    ON rpi_score_history(protocol_slug, score_date);

INSERT INTO migrations (name) VALUES ('052_rpi_tables') ON CONFLICT DO NOTHING;

COMMIT;
