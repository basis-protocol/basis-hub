BEGIN;

ALTER TABLE assessment_events ADD COLUMN IF NOT EXISTS severity_ordinal INTEGER;

UPDATE assessment_events SET severity_ordinal = CASE severity
    WHEN 'silent' THEN 0
    WHEN 'notable' THEN 1
    WHEN 'alert' THEN 2
    WHEN 'critical' THEN 3
    ELSE 0
END;

CREATE INDEX IF NOT EXISTS idx_ae_severity_ordinal ON assessment_events(severity_ordinal, created_at DESC);

INSERT INTO migrations (name) VALUES ('015_severity_ordinal') ON CONFLICT DO NOTHING;

COMMIT;
