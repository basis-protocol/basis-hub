-- Migration 056: Collector performance stats per cycle
CREATE TABLE IF NOT EXISTS collector_cycle_stats (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    collector_name TEXT NOT NULL,
    coins_ok INTEGER NOT NULL DEFAULT 0,
    coins_timeout INTEGER NOT NULL DEFAULT 0,
    coins_error INTEGER NOT NULL DEFAULT 0,
    avg_latency_ms INTEGER NOT NULL DEFAULT 0,
    total_components INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_collector_stats_created
    ON collector_cycle_stats(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_collector_stats_name
    ON collector_cycle_stats(collector_name, created_at DESC);

INSERT INTO migrations (name) VALUES ('056_collector_stats') ON CONFLICT DO NOTHING;
