-- Migration 076: Retroactive Backfill with Confidence Surface (Bucket A3)
-- Continuous historical score series for every scored entity, walking
-- forward from contract deployment at weekly intervals. Every row has a
-- confidence tag derived from how many of the methodology's components
-- were available at that historical moment. The full input vector is
-- stored alongside so any score can be re-derived later.

CREATE TABLE IF NOT EXISTS historical_score_backfill (
    id                       SERIAL PRIMARY KEY,
    index_kind               VARCHAR(20) NOT NULL,    -- psi | rpi | lsti | bri | dohi | vsri | cxri | tti
    entity_slug              VARCHAR(160) NOT NULL,
    snapshot_date            DATE NOT NULL,           -- weekly walk-forward date
    deployment_date          DATE,                    -- on-chain deployment date for the entity
    weeks_since_deployment   INTEGER,

    score                    DECIMAL(6,2),
    grade                    VARCHAR(2),

    methodology_version      VARCHAR(20) NOT NULL,
    component_scores         JSONB,
    components_available     INTEGER NOT NULL DEFAULT 0,
    components_total         INTEGER NOT NULL DEFAULT 0,
    coverage_pct             DECIMAL(5,2),
    confidence_tag           VARCHAR(20),             -- high | medium | low | sparse | bootstrap

    -- Reproducibility
    input_vector             JSONB NOT NULL,          -- complete inputs used to compute this score
    input_vector_hash        VARCHAR(80) NOT NULL,
    computation_hash         VARCHAR(80) NOT NULL,

    notes                    TEXT,
    computed_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (index_kind, entity_slug, snapshot_date, methodology_version)
);

CREATE INDEX IF NOT EXISTS idx_historical_backfill_entity_date
    ON historical_score_backfill (index_kind, entity_slug, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_historical_backfill_kind_date
    ON historical_score_backfill (index_kind, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_historical_backfill_confidence
    ON historical_score_backfill (confidence_tag);

INSERT INTO migrations (name) VALUES ('076_historical_score_backfill') ON CONFLICT DO NOTHING;
