BEGIN;

ALTER TABLE assessment_events ADD COLUMN IF NOT EXISTS inputs_hash VARCHAR(66);
ALTER TABLE assessment_events ADD COLUMN IF NOT EXISTS inputs_summary JSONB;

INSERT INTO migrations (name) VALUES ('016_inputs_hash') ON CONFLICT DO NOTHING;

COMMIT;
