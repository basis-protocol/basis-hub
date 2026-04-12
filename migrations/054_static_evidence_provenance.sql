-- Migration 054: Static evidence provenance tracking
-- Links TLSNotary proofs to static component evidence records.
-- Three evidence types per component: HTML snapshot, screenshot, TLSNotary proof.

CREATE TABLE IF NOT EXISTS static_evidence (
    id SERIAL PRIMARY KEY,
    index_id VARCHAR(20) NOT NULL,
    entity_slug VARCHAR(100) NOT NULL,
    component_name VARCHAR(100) NOT NULL,
    source_url TEXT NOT NULL,
    source_category VARCHAR(20) NOT NULL,

    -- Current extracted value
    current_value TEXT,
    value_updated_at TIMESTAMP WITH TIME ZONE,

    -- Evidence layer 1: HTML snapshot
    snapshot_html TEXT,
    snapshot_captured_at TIMESTAMP WITH TIME ZONE,
    snapshot_r2_path TEXT,

    -- Evidence layer 2: Screenshot
    screenshot_r2_path TEXT,
    screenshot_captured_at TIMESTAMP WITH TIME ZONE,

    -- Evidence layer 3: TLSNotary proof
    proof_r2_path TEXT,
    proof_captured_at TIMESTAMP WITH TIME ZONE,
    proof_attestation_hash VARCHAR(66),
    proof_response_hash VARCHAR(66),
    proof_captured_range VARCHAR(30),
    proof_http_status SMALLINT,
    proof_size_bytes INTEGER,

    -- Combined evidence hash: SHA-256(proof.bin || screenshot.png || snapshot.html)
    evidence_hash VARCHAR(66),

    -- Attestor identity
    attestor_pubkey TEXT,

    -- Staleness tracking
    last_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    check_interval_hours INTEGER DEFAULT 168,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(index_id, entity_slug, component_name)
);

CREATE INDEX IF NOT EXISTS idx_static_evidence_entity
    ON static_evidence(index_id, entity_slug);
CREATE INDEX IF NOT EXISTS idx_static_evidence_proof
    ON static_evidence(proof_attestation_hash)
    WHERE proof_attestation_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_static_evidence_staleness
    ON static_evidence(last_checked_at, check_interval_hours);

-- History table for tracking evidence changes over time
CREATE TABLE IF NOT EXISTS static_evidence_history (
    id SERIAL PRIMARY KEY,
    evidence_id INTEGER REFERENCES static_evidence(id),
    previous_value TEXT,
    new_value TEXT,
    change_type VARCHAR(20) NOT NULL,
    proof_attestation_hash VARCHAR(66),
    evidence_hash VARCHAR(66),
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_static_evidence_history_eid
    ON static_evidence_history(evidence_id, captured_at DESC);

INSERT INTO migrations (name) VALUES ('054_static_evidence_provenance') ON CONFLICT DO NOTHING;
