-- Migration 032: Ops Hub Session 5-6 additions
-- Target surface URLs, alert config, analytics views

-- Add surface_urls to targets (blog, forum, twitter, github URLs to monitor)
ALTER TABLE ops_targets ADD COLUMN IF NOT EXISTS surface_urls JSONB DEFAULT '[]'::jsonb;

-- Alert configuration
CREATE TABLE IF NOT EXISTS ops_alert_config (
    id SERIAL PRIMARY KEY,
    channel TEXT NOT NULL,           -- 'telegram', 'email'
    config JSONB NOT NULL,           -- { "bot_token": "...", "chat_id": "..." } or { "to": "..." }
    enabled BOOLEAN DEFAULT TRUE,
    alert_types TEXT[] DEFAULT '{health_failure,engagement_response,milestone_change}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Alert log (what was sent, when)
CREATE TABLE IF NOT EXISTS ops_alert_log (
    id SERIAL PRIMARY KEY,
    alert_type TEXT NOT NULL,        -- 'health_failure', 'engagement_response', 'milestone_change', 'content_due'
    channel TEXT NOT NULL,
    message TEXT NOT NULL,
    context JSONB,
    sent_at TIMESTAMP DEFAULT NOW(),
    acknowledged BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_ops_alert_log_time ON ops_alert_log(sent_at);

-- CoinGecko news cache
CREATE TABLE IF NOT EXISTS ops_coingecko_news (
    id SERIAL PRIMARY KEY,
    news_id TEXT UNIQUE,             -- CoinGecko news item ID
    title TEXT NOT NULL,
    description TEXT,
    url TEXT,
    thumb TEXT,
    source TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT NOW(),
    -- Analysis
    stablecoin_relevant BOOLEAN DEFAULT FALSE,
    relevant_symbols TEXT[],
    incident_detected BOOLEAN DEFAULT FALSE,
    draft_angle TEXT,                -- Claude-generated content angle
    actioned BOOLEAN DEFAULT FALSE
);

-- Track migration
INSERT INTO migrations (name, applied_at)
VALUES ('032_ops_surfaces_alerts', NOW())
ON CONFLICT DO NOTHING;
