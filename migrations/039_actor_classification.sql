-- Migration 039: Actor Classification (Primitive #21)
-- Adds actor type classification to the wallet graph.

-- Actor classifications — one row per wallet
CREATE TABLE IF NOT EXISTS wallet_graph.actor_classifications (
    wallet_address TEXT PRIMARY KEY,
    actor_type TEXT NOT NULL DEFAULT 'unknown',
    agent_probability REAL NOT NULL DEFAULT 0.5,
    confidence TEXT NOT NULL DEFAULT 'low',
    feature_vector JSONB,
    tx_count_basis INTEGER NOT NULL DEFAULT 0,
    methodology_version TEXT NOT NULL DEFAULT 'ACL-v1.0',
    classification_hash TEXT,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actor_type ON wallet_graph.actor_classifications(actor_type);
CREATE INDEX IF NOT EXISTS idx_actor_classified_at ON wallet_graph.actor_classifications(classified_at);

-- Classification history (compounding state — reclassifications over time)
CREATE TABLE IF NOT EXISTS wallet_graph.actor_classification_history (
    id SERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    agent_probability REAL NOT NULL,
    previous_type TEXT,
    methodology_version TEXT NOT NULL DEFAULT 'ACL-v1.0',
    classified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actor_history_wallet ON wallet_graph.actor_classification_history(wallet_address);
CREATE INDEX IF NOT EXISTS idx_actor_history_at ON wallet_graph.actor_classification_history(classified_at);

-- Denormalized columns on wallet_profiles for query performance
ALTER TABLE wallet_graph.wallet_profiles
    ADD COLUMN IF NOT EXISTS actor_type TEXT DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS agent_probability REAL DEFAULT 0.5;
