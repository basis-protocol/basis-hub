-- Migration 102: Cycle Errors — records swallowed exceptions from supervision wrapper

CREATE TABLE IF NOT EXISTS cycle_errors (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    error_type TEXT NOT NULL,
    error_message TEXT,
    traceback TEXT,
    cycle_phase TEXT,
    severity TEXT NOT NULL DEFAULT 'caught',
    consecutive_failure_count INTEGER
);

CREATE INDEX IF NOT EXISTS idx_cycle_errors_occurred ON cycle_errors (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_cycle_errors_type ON cycle_errors (error_type, occurred_at DESC);

INSERT INTO migrations (name) VALUES ('102_cycle_errors') ON CONFLICT DO NOTHING;
