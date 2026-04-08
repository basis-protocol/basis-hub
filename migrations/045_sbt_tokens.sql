-- Migration 045: SBT token tracking table
CREATE TABLE IF NOT EXISTS sbt_tokens (
    token_id INTEGER PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    chain VARCHAR(20) NOT NULL DEFAULT 'base',
    contract_address VARCHAR(42) NOT NULL,
    score NUMERIC(6,2),
    grade VARCHAR(3),
    confidence VARCHAR(10),
    report_hash VARCHAR(64),
    method_version VARCHAR(10),
    minted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sbt_entity ON sbt_tokens(entity_type, entity_id);

INSERT INTO migrations (name) VALUES ('045_sbt_tokens') ON CONFLICT DO NOTHING;
