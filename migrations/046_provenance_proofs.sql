CREATE TABLE IF NOT EXISTS provenance_proofs (
    id SERIAL PRIMARY KEY,
    source_domain TEXT NOT NULL,
    source_endpoint TEXT NOT NULL,
    response_hash VARCHAR(66) NOT NULL,
    attestation_hash VARCHAR(66) NOT NULL,
    proof_url TEXT NOT NULL,
    attestor_pubkey TEXT NOT NULL,
    proof_size_bytes INTEGER,
    proved_at TIMESTAMP WITH TIME ZONE NOT NULL,
    registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    cycle_hour TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prov_domain_hour ON provenance_proofs (source_domain, cycle_hour);
CREATE INDEX IF NOT EXISTS idx_prov_attestation ON provenance_proofs (attestation_hash);
CREATE INDEX IF NOT EXISTS idx_prov_cycle ON provenance_proofs (cycle_hour);
