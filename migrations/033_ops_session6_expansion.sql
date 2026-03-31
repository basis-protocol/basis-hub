-- Migration 033: Session 6 expansion — investor content, governance tracking
-- Twitter monitoring, Snapshot/Tally governance, investor blog/tweet monitoring

-- Investor content (VC blogs, tweets, portfolio announcements)
CREATE TABLE IF NOT EXISTS ops_investor_content (
    id SERIAL PRIMARY KEY,
    investor_id INTEGER REFERENCES ops_investors(id),
    source_url TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,          -- 'blog', 'tweet', 'portfolio_announcement', 'research'
    title TEXT,
    content TEXT NOT NULL,
    content_summary TEXT,
    published_at TIMESTAMP,
    scraped_at TIMESTAMP DEFAULT NOW(),
    -- Analysis
    analyzed BOOLEAN DEFAULT FALSE,
    thesis_extract TEXT,                -- what investment thesis does this express
    alignment_score REAL,              -- 0-1, how aligned with Basis thesis
    alignment_notes TEXT,              -- why this is relevant for outreach
    outreach_angle TEXT,               -- drafted outreach angle based on content
    timing_signal BOOLEAN DEFAULT FALSE, -- does this suggest good timing for outreach
    timing_notes TEXT,
    -- Action
    actioned BOOLEAN DEFAULT FALSE,
    action_taken TEXT
);

CREATE INDEX IF NOT EXISTS idx_ops_investor_content_investor ON ops_investor_content(investor_id);
CREATE INDEX IF NOT EXISTS idx_ops_investor_content_scraped ON ops_investor_content(scraped_at);

-- Governance proposals tracked from Snapshot/Tally
-- Stored in ops_target_content with source_type 'snapshot_vote' or 'governance_proposal'
-- but we add a dedicated tracking table for proposal metadata
CREATE TABLE IF NOT EXISTS ops_governance_proposals (
    id SERIAL PRIMARY KEY,
    target_id INTEGER REFERENCES ops_targets(id),
    platform TEXT NOT NULL,             -- 'snapshot', 'tally', 'forum'
    proposal_id TEXT NOT NULL,          -- platform-specific ID
    space_or_org TEXT,                  -- Snapshot space ID or Tally org
    title TEXT NOT NULL,
    body TEXT,
    state TEXT,                         -- 'active', 'closed', 'pending', 'executed'
    vote_type TEXT,                     -- 'single-choice', 'weighted', 'approval', 'quadratic'
    choices TEXT[],
    scores REAL[],
    votes_count INTEGER,
    start_at TIMESTAMP,
    end_at TIMESTAMP,
    author TEXT,
    -- Stablecoin relevance
    stablecoin_relevant BOOLEAN DEFAULT FALSE,
    relevant_coins TEXT[],              -- which stablecoins are mentioned
    relevance_notes TEXT,
    -- Linked content analysis
    content_id INTEGER,                 -- FK to ops_target_content if analyzed
    fetched_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(platform, proposal_id)
);

CREATE INDEX IF NOT EXISTS idx_ops_gov_proposals_target ON ops_governance_proposals(target_id);
CREATE INDEX IF NOT EXISTS idx_ops_gov_proposals_state ON ops_governance_proposals(state);
CREATE INDEX IF NOT EXISTS idx_ops_gov_proposals_relevant ON ops_governance_proposals(stablecoin_relevant);

-- Track migration
INSERT INTO migrations (name, applied_at)
VALUES ('033_ops_session6_expansion', NOW())
ON CONFLICT DO NOTHING;
