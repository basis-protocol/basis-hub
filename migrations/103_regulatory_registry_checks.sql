-- Ensure regulatory_registry_checks table and ON CONFLICT-compatible
-- unique index exist on production. Migration 055 originally defined
-- both, but production logs (2026-05-01) show the table was missing,
-- causing repeated "relation regulatory_registry_checks does not exist"
-- errors from app/collectors/regulatory_scraper.py for every CXRI run.
--
-- Schema mirrors migration 055. The expression-index unique constraint
-- in 055 (`(entity_slug, registry_name, checked_at::date)`) cannot
-- satisfy the ON CONFLICT (entity_slug, registry_name) clause in
-- regulatory_scraper.py:388, so this migration also ensures the simple
-- unique index that the scraper otherwise tries to create at runtime
-- (lines 381-386) exists up-front.
--
-- Fully idempotent — safe to re-run.

CREATE TABLE IF NOT EXISTS regulatory_registry_checks (
    id SERIAL PRIMARY KEY,
    entity_slug TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- 'cex', 'tti_issuer', etc.
    registry_name TEXT NOT NULL,
    registry_url TEXT,
    is_listed BOOLEAN,
    license_type TEXT,
    registration_date TEXT,
    enforcement_actions JSONB,
    raw_content TEXT,
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- Simple unique index required for ON CONFLICT (entity_slug, registry_name)
-- in regulatory_scraper.py:394. Same as the runtime-created index at
-- regulatory_scraper.py:382 (idx_reg_check_entity_registry_simple).
-- Note: migration 055 originally also defined an expression-based unique
-- index `idx_reg_check_entity_registry ON (entity_slug, registry_name,
-- checked_at::date)`. That index cannot satisfy ON CONFLICT (which the
-- application actually needs) so it is dead; not duplicated here.
CREATE UNIQUE INDEX IF NOT EXISTS idx_reg_check_entity_registry_simple
    ON regulatory_registry_checks(entity_slug, registry_name);

CREATE INDEX IF NOT EXISTS idx_reg_check_entity
    ON regulatory_registry_checks(entity_slug);

INSERT INTO migrations (name) VALUES ('103_regulatory_registry_checks') ON CONFLICT DO NOTHING;
