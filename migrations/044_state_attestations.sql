-- Migration 044: Universal state attestation table
-- Every domain of novel state gets hashed per cycle

CREATE TABLE IF NOT EXISTS state_attestations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain VARCHAR(30) NOT NULL,
    entity_id VARCHAR(200),
    batch_hash VARCHAR(64) NOT NULL,
    record_count INTEGER NOT NULL,
    methodology_version VARCHAR(20),
    cycle_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_state_attestations_domain
    ON state_attestations(domain, cycle_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_state_attestations_entity
    ON state_attestations(domain, entity_id, cycle_timestamp DESC);

-- Migrate existing component_batch_hashes into state_attestations
INSERT INTO state_attestations (domain, entity_id, batch_hash, record_count, methodology_version, cycle_timestamp)
SELECT 'sii_components', entity_id, batch_hash, component_count, methodology_version, computed_at
FROM component_batch_hashes
ON CONFLICT DO NOTHING;

INSERT INTO migrations (name) VALUES ('044_state_attestations') ON CONFLICT DO NOTHING;
