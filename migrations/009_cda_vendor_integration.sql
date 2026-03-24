-- Migration 009: CDA Vendor Integration (Phase 1)
-- Adds vendor extraction overlay table and issuer registry for CDA pipeline.
-- Does NOT modify any existing tables.

-- Vendor extraction results (Option B — overlay table)
CREATE TABLE IF NOT EXISTS cda_vendor_extractions (
    id SERIAL PRIMARY KEY,
    asset_symbol VARCHAR(20) NOT NULL,
    source_url TEXT NOT NULL,
    source_type VARCHAR(30) NOT NULL,
    extraction_method VARCHAR(30) NOT NULL,
    extraction_vendor VARCHAR(30) NOT NULL,
    raw_response JSONB,
    structured_data JSONB,
    confidence_score NUMERIC,
    extraction_warnings TEXT[],
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cda_vendor_symbol ON cda_vendor_extractions(asset_symbol);
CREATE INDEX IF NOT EXISTS idx_cda_vendor_date ON cda_vendor_extractions(extracted_at DESC);

-- Issuer registry for CDA collection
CREATE TABLE IF NOT EXISTS cda_issuer_registry (
    id SERIAL PRIMARY KEY,
    asset_symbol VARCHAR(20) NOT NULL UNIQUE,
    issuer_name VARCHAR(100) NOT NULL,
    coingecko_id VARCHAR(100),
    transparency_url TEXT,
    attestation_page_url TEXT,
    collection_method VARCHAR(30) DEFAULT 'web_extract',
    asset_category VARCHAR(30),
    is_active BOOLEAN DEFAULT TRUE,
    last_successful_collection TIMESTAMPTZ,
    consecutive_failures INT DEFAULT 0,
    last_failure_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
