-- Migration 013: API usage tracking tables
-- api_keys: stores API keys for authenticated (higher rate limit) access
-- api_request_log: per-request audit log, bulk-inserted from in-memory buffer

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    total_requests BIGINT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS api_request_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INT,
    response_time_ms INT,
    ip_address VARCHAR(45),
    api_key_id INT REFERENCES api_keys(id),
    api_key_hash VARCHAR(64),
    user_agent VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS idx_request_log_timestamp ON api_request_log (timestamp);
CREATE INDEX IF NOT EXISTS idx_request_log_endpoint ON api_request_log (endpoint, timestamp);
CREATE INDEX IF NOT EXISTS idx_request_log_api_key ON api_request_log (api_key_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_request_log_key_hash ON api_request_log (api_key_hash) WHERE api_key_hash IS NOT NULL;

INSERT INTO migrations (name) VALUES ('013_api_usage') ON CONFLICT DO NOTHING;
