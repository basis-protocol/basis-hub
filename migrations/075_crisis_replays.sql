-- Migration 075: Crisis Replay Library (Bucket A2)
-- One row per (crisis_slug, index_kind) replay. Stores the canonical input
-- vector hash, the methodology version that was applied, the SHA-256 of the
-- computation, and the final scores produced. The replay harness lives in
-- crisis_replays/ on disk and links back to these rows via the slug.

CREATE TABLE IF NOT EXISTS crisis_replays (
    id                   SERIAL PRIMARY KEY,
    crisis_slug          VARCHAR(80) NOT NULL,        -- terra-luna, ftx, usdc-svb, ...
    crisis_label         VARCHAR(160) NOT NULL,
    crisis_date          DATE NOT NULL,               -- canonical date the crisis became active

    index_kind           VARCHAR(20) NOT NULL,        -- sii | psi | rpi | cqi
    entity_slug          VARCHAR(120),                -- optional — which entity the score is for
    methodology_version  VARCHAR(20) NOT NULL,

    -- Cryptographic attestation of the replay
    input_vector_hash    VARCHAR(80) NOT NULL,        -- sha256 of canonical input components
    computation_hash     VARCHAR(80) NOT NULL,        -- sha256 of (input_vector_hash || method_version || final_scores)
    input_summary        JSONB,                       -- redacted summary of inputs (for display)

    -- Outputs
    final_score          DECIMAL(6,2),
    final_grade          VARCHAR(2),
    component_scores     JSONB,
    pre_crisis_score     DECIMAL(6,2),                -- the score we would have produced just before
    delta                DECIMAL(7,2),                -- final_score - pre_crisis_score

    -- Re-derivation pointers
    replay_script_path   VARCHAR(200),                -- path within crisis_replays/ to the harness
    reference_url        VARCHAR(400),
    notes                TEXT,

    computed_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (crisis_slug, index_kind, entity_slug, methodology_version)
);

CREATE INDEX IF NOT EXISTS idx_crisis_replays_slug
    ON crisis_replays (crisis_slug);
CREATE INDEX IF NOT EXISTS idx_crisis_replays_date
    ON crisis_replays (crisis_date DESC);
CREATE INDEX IF NOT EXISTS idx_crisis_replays_kind
    ON crisis_replays (index_kind);

INSERT INTO migrations (name) VALUES ('075_crisis_replays') ON CONFLICT DO NOTHING;
