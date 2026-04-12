-- Phase 3: TTI Disclosure Extractions + Regulatory Registry Checks
-- Supports CDA-pattern extension for issuer disclosure parsing and regulatory scraping

-- TTI issuer disclosure extractions (follows cda_vendor_extractions pattern)
CREATE TABLE IF NOT EXISTS tti_disclosure_extractions (
    id SERIAL PRIMARY KEY,
    entity_slug TEXT NOT NULL,
    entity_name TEXT,
    source_url TEXT NOT NULL,
    source_type TEXT NOT NULL,  -- 'product_page', 'attestation_pdf', 'prospectus', 'fact_sheet'
    structured_data JSONB NOT NULL,
    extraction_method TEXT,    -- 'firecrawl_markdown', 'reducto_pdf', 'firecrawl_json'
    confidence REAL,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tti_disc_entity_date
    ON tti_disclosure_extractions(entity_slug, source_url, extracted_at::date);

CREATE INDEX IF NOT EXISTS idx_tti_disc_slug
    ON tti_disclosure_extractions(entity_slug);

-- Regulatory registry checks (used by CXRI + potentially TTI issuers)
CREATE TABLE IF NOT EXISTS regulatory_registry_checks (
    id SERIAL PRIMARY KEY,
    entity_slug TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- 'cex', 'tti_issuer', etc.
    registry_name TEXT NOT NULL,
    registry_url TEXT,
    is_listed BOOLEAN,
    license_type TEXT,
    registration_date TEXT,
    enforcement_actions JSONB,
    raw_content TEXT,          -- snippet of relevant page content
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_check_entity_registry
    ON regulatory_registry_checks(entity_slug, registry_name, checked_at::date);

CREATE INDEX IF NOT EXISTS idx_reg_check_entity
    ON regulatory_registry_checks(entity_slug);

-- VSRI documentation scores (reuses rpi_doc_scores pattern but for vault entities)
-- No new table needed — rpi_doc_scores already supports arbitrary protocol_slug values
