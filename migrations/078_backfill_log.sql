-- Migration 078: Backfill run tracking table

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS backfill_runs (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    index_name TEXT NOT NULL,
    entity_slug TEXT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    rows_written INTEGER DEFAULT 0,
    rows_failed INTEGER DEFAULT 0,
    source_used TEXT,
    block_range INT8RANGE,
    error TEXT,
    coherence_failure_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_backfill_runs_index
    ON backfill_runs (index_name, entity_slug);
CREATE INDEX IF NOT EXISTS idx_backfill_runs_incomplete
    ON backfill_runs (completed_at) WHERE completed_at IS NULL;

INSERT INTO migrations (name) VALUES ('078_backfill_log') ON CONFLICT DO NOTHING;
