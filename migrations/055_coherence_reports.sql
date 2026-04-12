-- Migration 055: Coherence reports table for cross-domain consistency validation
CREATE TABLE IF NOT EXISTS coherence_reports (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    domains_checked INTEGER NOT NULL,
    issues_found INTEGER NOT NULL,
    details JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_coherence_reports_created
    ON coherence_reports(created_at DESC);

INSERT INTO migrations (name) VALUES ('055_coherence_reports') ON CONFLICT DO NOTHING;
