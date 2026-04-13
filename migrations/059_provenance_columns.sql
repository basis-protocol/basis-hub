-- Migration 059: Provenance coverage for universal data layer
-- Adds provenance_proof_id columns to all data layer tables
-- Links each data batch to its nearest TLSNotary proof

-- Add provenance_proof_id to all universal data layer tables
ALTER TABLE liquidity_depth ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE yield_snapshots ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE governance_proposals ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE governance_voters ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE bridge_flows ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE exchange_snapshots ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE correlation_matrices ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE volatility_surfaces ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE incident_events ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE peg_snapshots_5m ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE mint_burn_events ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE entity_snapshots_hourly ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE contract_surveillance ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);
ALTER TABLE wallet_behavior_tags ADD COLUMN IF NOT EXISTS provenance_proof_id INTEGER REFERENCES provenance_proofs(id);

-- Indexes for provenance joins (only on high-volume tables)
CREATE INDEX IF NOT EXISTS idx_liquidity_prov ON liquidity_depth(provenance_proof_id) WHERE provenance_proof_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_peg5m_prov ON peg_snapshots_5m(provenance_proof_id) WHERE provenance_proof_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mintburn_prov ON mint_burn_events(provenance_proof_id) WHERE provenance_proof_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_snap_prov ON entity_snapshots_hourly(provenance_proof_id) WHERE provenance_proof_id IS NOT NULL;

-- CDA provenance: add last_notarized_hash for Range header approach
ALTER TABLE cda_source_urls ADD COLUMN IF NOT EXISTS last_notarized_hash VARCHAR(66);
ALTER TABLE cda_source_urls ADD COLUMN IF NOT EXISTS content_length BIGINT;
ALTER TABLE cda_source_urls ADD COLUMN IF NOT EXISTS range_header_used BOOLEAN DEFAULT FALSE;

INSERT INTO migrations (name) VALUES ('059_provenance_columns') ON CONFLICT DO NOTHING;
