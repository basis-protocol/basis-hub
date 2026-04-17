-- Migration 077: Dispute Infrastructure (Bucket A4)
-- Anyone can dispute a score by referencing its hash. Every state
-- transition (submission, counter-evidence, resolution) is hashed and
-- committed on-chain via Oracle V2 publishDisputeHash.

CREATE TABLE IF NOT EXISTS disputes (
    id                        SERIAL PRIMARY KEY,
    entity_slug               VARCHAR(160) NOT NULL,
    index_kind                VARCHAR(20),             -- sii | psi | rpi | cqi
    score_hash_disputed       VARCHAR(80) NOT NULL,
    score_value_disputed      DECIMAL(6,2),

    -- Submission
    submitter_address         VARCHAR(80) NOT NULL,
    submission_payload        JSONB NOT NULL,
    submission_hash           VARCHAR(80) NOT NULL,
    submission_timestamp      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Counter-evidence (Basis can attach data confirming or rejecting the claim)
    counter_evidence_payload  JSONB,
    counter_evidence_hash     VARCHAR(80),
    counter_evidence_at       TIMESTAMPTZ,

    -- Resolution
    resolution_status         VARCHAR(20) DEFAULT 'open',  -- open | upheld | rejected | partially_upheld | withdrawn
    resolution_payload        JSONB,
    resolution_hash           VARCHAR(80),
    resolution_timestamp      TIMESTAMPTZ,
    resolver                  VARCHAR(120),

    -- On-chain anchoring (one row per state transition; we keep the latest tx here for convenience)
    on_chain_commit_tx        VARCHAR(80),
    on_chain_chain            VARCHAR(20),
    on_chain_committed_at     TIMESTAMPTZ,

    created_at                TIMESTAMPTZ DEFAULT NOW(),
    updated_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_disputes_entity
    ON disputes (entity_slug);
CREATE INDEX IF NOT EXISTS idx_disputes_status
    ON disputes (resolution_status);
CREATE INDEX IF NOT EXISTS idx_disputes_submitter
    ON disputes (submitter_address);
CREATE INDEX IF NOT EXISTS idx_disputes_open
    ON disputes (submission_timestamp DESC)
    WHERE resolution_status = 'open';

-- Per-transition audit trail (every state change is its own row + on-chain tx)
CREATE TABLE IF NOT EXISTS dispute_commitments (
    id                   SERIAL PRIMARY KEY,
    dispute_id           INTEGER NOT NULL REFERENCES disputes(id) ON DELETE CASCADE,
    transition_kind      VARCHAR(30) NOT NULL,        -- submission | counter_evidence | resolution
    commitment_hash      VARCHAR(80) NOT NULL,
    on_chain_tx_hash     VARCHAR(80),
    on_chain_chain       VARCHAR(20),
    on_chain_block       BIGINT,
    committed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispute_commitments_dispute
    ON dispute_commitments (dispute_id, committed_at DESC);

INSERT INTO migrations (name) VALUES ('077_disputes') ON CONFLICT DO NOTHING;
