-- Migration 005: Create legacy_data_provenance table for historical provenance data import
-- Source: neon_data_provenance.sql + replit_data_provenance.sql

CREATE TABLE IF NOT EXISTS legacy_data_provenance (
    id INTEGER PRIMARY KEY,
    stablecoin VARCHAR(50),
    component_id VARCHAR(100),
    component_name TEXT,
    category VARCHAR(50),
    raw_value TEXT,
    normalized_score NUMERIC(10,2),
    normalization_function VARCHAR(50),
    normalization_description TEXT,
    source_name VARCHAR(100),
    source_url TEXT,
    source_document TEXT,
    document_page TEXT,
    extracted_text TEXT,
    fetched_at TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    metadata JSONB,
    created_at TIMESTAMPTZ,
    raw_response TEXT,
    run_id TEXT,
    processor_tier TEXT,
    field_confidence TEXT,
    citations TEXT
);

INSERT INTO migrations (name, applied_at) VALUES ('005_data_provenance', NOW()) ON CONFLICT DO NOTHING;
