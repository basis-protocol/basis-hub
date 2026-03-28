BEGIN;

CREATE TABLE IF NOT EXISTS psi_scores (
    id SERIAL PRIMARY KEY,
    protocol_slug VARCHAR(100) NOT NULL,
    protocol_name VARCHAR(200),
    overall_score DOUBLE PRECISION,
    grade VARCHAR(2),
    category_scores JSONB,
    component_scores JSONB,
    raw_values JSONB,
    formula_version VARCHAR(20) DEFAULT 'psi-v0.1.0',
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    scored_date DATE DEFAULT CURRENT_DATE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_psi_unique_per_day
    ON psi_scores(protocol_slug, scored_date);

ALTER TABLE psi_scores ADD CONSTRAINT psi_scores_protocol_slug_scored_date_key
    UNIQUE USING INDEX idx_psi_unique_per_day;

INSERT INTO migrations (name) VALUES ('017_psi_scores') ON CONFLICT DO NOTHING;

COMMIT;
