-- Migration 077: Add backfill tracking columns to historical score tables
-- Nullable on existing rows. Used by backfill scripts to mark reconstructed data.

ALTER TABLE score_history ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE;
ALTER TABLE score_history ADD COLUMN IF NOT EXISTS backfill_source TEXT;

ALTER TABLE psi_scores ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE;
ALTER TABLE psi_scores ADD COLUMN IF NOT EXISTS backfill_source TEXT;

ALTER TABLE rpi_score_history ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE;
ALTER TABLE rpi_score_history ADD COLUMN IF NOT EXISTS backfill_source TEXT;

ALTER TABLE generic_index_scores ADD COLUMN IF NOT EXISTS backfilled BOOLEAN DEFAULT FALSE;
ALTER TABLE generic_index_scores ADD COLUMN IF NOT EXISTS backfill_source TEXT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_score_history_backfill
    ON score_history (stablecoin, backfilled);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_psi_backfill
    ON psi_scores (protocol_slug, backfilled);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rpi_history_backfill
    ON rpi_score_history (protocol_slug, backfilled);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gis_backfill
    ON generic_index_scores (entity_slug, backfilled);

INSERT INTO migrations (name) VALUES ('077_backfill_flag') ON CONFLICT DO NOTHING;
