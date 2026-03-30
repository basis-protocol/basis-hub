BEGIN;

CREATE TABLE IF NOT EXISTS backfill_status (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'completed', 'failed'
    coins_total INTEGER,
    coins_completed INTEGER DEFAULT 0,
    records_total INTEGER DEFAULT 0,
    current_coin VARCHAR(50),
    error_message TEXT,
    details JSONB DEFAULT '{}'::jsonb
);

INSERT INTO migrations (name) VALUES ('030_backfill_status') ON CONFLICT DO NOTHING;

COMMIT;
