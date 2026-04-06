-- Migration 036: Track wallet expansion pagination progress per stablecoin
-- Allows the expander to resume from where it left off instead of always
-- re-fetching pages 1-5 (which are already fully indexed).

ALTER TABLE stablecoins ADD COLUMN IF NOT EXISTS expansion_last_page INTEGER DEFAULT 0;
ALTER TABLE stablecoins ADD COLUMN IF NOT EXISTS expansion_exhausted BOOLEAN DEFAULT FALSE;

INSERT INTO migrations (name, applied_at)
VALUES ('036_expander_page_tracking', NOW())
ON CONFLICT DO NOTHING;
