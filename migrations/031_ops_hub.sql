-- Migration 031: Operations Hub tables
-- GTM target tracking, pipeline health, fundraise pipeline, content management

-- Targets
CREATE TABLE IF NOT EXISTS ops_targets (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    track TEXT,
    tier INTEGER NOT NULL DEFAULT 3,
    worldview_summary TEXT,
    gap TEXT,
    first_wedge TEXT,
    landmine TEXT,
    positioning TEXT,
    pipeline_stage TEXT DEFAULT 'not_started',
    last_action_at TIMESTAMP,
    next_action TEXT,
    next_action_due TIMESTAMP,
    wallet_addresses TEXT[],
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Target contacts
CREATE TABLE IF NOT EXISTS ops_target_contacts (
    id SERIAL PRIMARY KEY,
    target_id INTEGER REFERENCES ops_targets(id),
    name TEXT NOT NULL,
    role TEXT,
    twitter_handle TEXT,
    linkedin_url TEXT,
    forum_username TEXT,
    email TEXT,
    warmth INTEGER,
    warm_path TEXT,
    notes TEXT
);

-- Target content (scraped + analyzed)
CREATE TABLE IF NOT EXISTS ops_target_content (
    id SERIAL PRIMARY KEY,
    target_id INTEGER REFERENCES ops_targets(id),
    source_url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    content_summary TEXT,
    published_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT NOW(),
    analyzed BOOLEAN DEFAULT FALSE,
    worldview_extract TEXT,
    bridge_found BOOLEAN,
    bridge_text TEXT,
    draft_comment TEXT,
    comment_type TEXT,
    engagement_action TEXT,
    relevance_score REAL,
    founder_decision TEXT,
    founder_edited_text TEXT,
    posted_at TIMESTAMP,
    engagement_received TEXT
);

-- Engagement log
CREATE TABLE IF NOT EXISTS ops_target_engagement_log (
    id SERIAL PRIMARY KEY,
    target_id INTEGER REFERENCES ops_targets(id),
    contact_id INTEGER REFERENCES ops_target_contacts(id),
    action_type TEXT NOT NULL,
    content TEXT,
    channel TEXT,
    response TEXT,
    response_at TIMESTAMP,
    next_action TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Exposure reports
CREATE TABLE IF NOT EXISTS ops_target_exposure_reports (
    id SERIAL PRIMARY KEY,
    target_id INTEGER REFERENCES ops_targets(id),
    wallet_addresses TEXT[],
    report_data JSONB,
    report_markdown TEXT,
    generated_at TIMESTAMP DEFAULT NOW(),
    sent_at TIMESTAMP,
    sent_to TEXT
);

-- Investors
CREATE TABLE IF NOT EXISTS ops_investors (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    firm TEXT,
    tier INTEGER NOT NULL,
    stage TEXT DEFAULT 'not_started',
    key_person TEXT,
    warm_path TEXT,
    thesis_alignment TEXT,
    materials_sent TEXT[],
    last_action TEXT,
    last_action_at TIMESTAMP,
    next_action TEXT,
    next_action_due TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Investor interactions
CREATE TABLE IF NOT EXISTS ops_investor_interactions (
    id SERIAL PRIMARY KEY,
    investor_id INTEGER REFERENCES ops_investors(id),
    action_type TEXT NOT NULL,
    content TEXT,
    response TEXT,
    occurred_at TIMESTAMP DEFAULT NOW(),
    next_step TEXT
);

-- Health checks
CREATE TABLE IF NOT EXISTS ops_health_checks (
    id SERIAL PRIMARY KEY,
    system TEXT NOT NULL,
    status TEXT NOT NULL,
    details JSONB,
    checked_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ops_health_time ON ops_health_checks(checked_at);

-- Content items
CREATE TABLE IF NOT EXISTS ops_content_items (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    target_channel TEXT,
    related_target_id INTEGER REFERENCES ops_targets(id),
    status TEXT DEFAULT 'draft',
    scheduled_for TIMESTAMP,
    posted_at TIMESTAMP,
    engagement_metrics JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Track migration
INSERT INTO migrations (name, applied_at)
VALUES ('031_ops_hub', NOW())
ON CONFLICT DO NOTHING;
