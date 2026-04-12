CREATE TABLE IF NOT EXISTS divergence_signals (
    id SERIAL PRIMARY KEY,
    detector_name TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    signal_direction TEXT,
    magnitude FLOAT,
    severity TEXT,
    detail JSONB,
    cycle_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_divergence_signals_entity ON divergence_signals(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_divergence_signals_time ON divergence_signals(cycle_timestamp DESC);

INSERT INTO migrations (name) VALUES ('053_divergence_signals') ON CONFLICT DO NOTHING;
