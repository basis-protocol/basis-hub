-- Migration 074: Track Record Commitments (Bucket A1)
-- Records every consequential event (divergence signal, RPI delta >10,
-- coherence drop, score change >5) and anchors it on-chain via the
-- Oracle V2 publishTrackRecord function. Outcomes are scored at 30/60/90
-- day horizons so the public can verify call quality after the fact.

CREATE TABLE IF NOT EXISTS track_record_commitments (
    id                   SERIAL PRIMARY KEY,
    event_type           VARCHAR(50) NOT NULL,    -- divergence | rpi_delta | coherence_drop | score_change
    entity_slug          VARCHAR(120) NOT NULL,
    event_payload        JSONB NOT NULL,          -- canonical event fields used to compute event_hash
    event_hash           VARCHAR(66) NOT NULL,    -- 0x + sha256 of canonical(event_payload)
    event_timestamp      TIMESTAMPTZ NOT NULL,

    -- Magnitude / direction (the "call" being made)
    magnitude            DECIMAL(12,4),           -- numeric magnitude of the move (interpretation depends on event_type)
    direction            VARCHAR(10),             -- up | down | neutral
    score_before         DECIMAL(6,2),
    score_after          DECIMAL(6,2),

    -- On-chain anchor
    on_chain_tx_hash     VARCHAR(80),
    on_chain_block       BIGINT,
    on_chain_chain       VARCHAR(20),
    state_root_at_event  VARCHAR(80),
    committed_at         TIMESTAMPTZ,

    -- Outcomes — populated by the outcome scorer at the relevant horizons
    outcome_30d          DECIMAL(12,4),
    outcome_60d          DECIMAL(12,4),
    outcome_90d          DECIMAL(12,4),
    outcome_30d_at       TIMESTAMPTZ,
    outcome_60d_at       TIMESTAMPTZ,
    outcome_90d_at       TIMESTAMPTZ,

    methodology_version  VARCHAR(20),
    notes                TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (event_hash)
);

CREATE INDEX IF NOT EXISTS idx_track_record_entity_time
    ON track_record_commitments (entity_slug, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_track_record_type_time
    ON track_record_commitments (event_type, event_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_track_record_pending_outcomes
    ON track_record_commitments (event_timestamp)
    WHERE outcome_90d IS NULL;
CREATE INDEX IF NOT EXISTS idx_track_record_pending_commit
    ON track_record_commitments (event_timestamp)
    WHERE on_chain_tx_hash IS NULL;

INSERT INTO migrations (name) VALUES ('074_track_record_commitments') ON CONFLICT DO NOTHING;
