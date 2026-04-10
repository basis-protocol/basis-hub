CREATE TABLE IF NOT EXISTS cda_source_urls (
    id SERIAL PRIMARY KEY,
    asset_symbol VARCHAR(20) NOT NULL,
    issuer VARCHAR(100),
    source_url TEXT NOT NULL,
    content_type VARCHAR(50) DEFAULT 'application/pdf',
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_notarized_at TIMESTAMP WITH TIME ZONE,
    active BOOLEAN DEFAULT TRUE
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_cda_url_unique ON cda_source_urls (asset_symbol, source_url);
CREATE INDEX IF NOT EXISTS idx_cda_active ON cda_source_urls (active) WHERE active = TRUE;
