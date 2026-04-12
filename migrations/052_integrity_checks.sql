CREATE TABLE IF NOT EXISTS integrity_checks (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    check_type TEXT NOT NULL,
    status TEXT NOT NULL,
    detail JSONB,
    cycle_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_integrity_domain_time ON integrity_checks(domain, cycle_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_integrity_status ON integrity_checks(status);

INSERT INTO migrations (name) VALUES ('052_integrity_checks') ON CONFLICT DO NOTHING;
