BEGIN;

-- Add disclosure type and verification metadata to issuer registry
ALTER TABLE cda_issuer_registry
  ADD COLUMN IF NOT EXISTS disclosure_type VARCHAR(30) DEFAULT 'fiat-reserve',
  ADD COLUMN IF NOT EXISTS expected_fields JSONB,
  ADD COLUMN IF NOT EXISTS verification_rules JSONB,
  ADD COLUMN IF NOT EXISTS source_urls JSONB,
  ADD COLUMN IF NOT EXISTS auditor_name VARCHAR(100),
  ADD COLUMN IF NOT EXISTS attestation_frequency_days INTEGER;

-- disclosure_type values:
--   'fiat-reserve'           — Circle, Tether, Paxos, First Digital
--   'synthetic-derivative'   — Ethena USDe
--   'overcollateralized'     — DAI/MakerDAO
--   'algorithmic'            — FRAX
--   'rwa-tokenized'          — USDY, BUIDL
--   'unknown'                — newly discovered

-- Validation results table
CREATE TABLE IF NOT EXISTS cda_validation_results (
    id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES cda_vendor_extractions(id),
    asset_symbol VARCHAR(20) NOT NULL,
    validated_at TIMESTAMPTZ DEFAULT NOW(),
    rules_applied JSONB NOT NULL,
    rules_passed INTEGER DEFAULT 0,
    rules_failed INTEGER DEFAULT 0,
    rules_total INTEGER DEFAULT 0,
    overall_status VARCHAR(20) DEFAULT 'unknown'
);
CREATE INDEX IF NOT EXISTS idx_cda_val_symbol ON cda_validation_results(asset_symbol, validated_at DESC);
CREATE INDEX IF NOT EXISTS idx_cda_val_extraction ON cda_validation_results(extraction_id);

-- Seed disclosure types for known stablecoins
UPDATE cda_issuer_registry SET disclosure_type = 'fiat-reserve',
  expected_fields = '["total_reserves_usd","total_supply","attestation_date","auditor_name","reserve_composition"]'::jsonb,
  verification_rules = '[{"rule":"reserves_gte_supply","description":"Total reserves >= total supply","severity":"critical"}]'::jsonb
WHERE asset_symbol IN ('USDC', 'USDT', 'FDUSD', 'TUSD', 'USDP', 'PYUSD', 'USD1', 'GUSD');

UPDATE cda_issuer_registry SET disclosure_type = 'synthetic-derivative',
  expected_fields = '["total_supply","backing_assets","custodians","open_interest","collateral_ratio","funding_rate","attestation_date"]'::jsonb,
  verification_rules = '[{"rule":"collateral_ratio_gte_1","description":"Collateral ratio >= 1.0","severity":"critical"},{"rule":"custodians_present","description":"At least one custodian listed","severity":"warning"}]'::jsonb,
  source_urls = '[{"url":"https://app.ethena.fi/dashboards/transparency","type":"dashboard","description":"Real-time transparency dashboard"},{"url":"https://docs.ethena.fi/resources/custodian-attestations","type":"attestation_page","description":"Custodian attestation reports"}]'::jsonb
WHERE asset_symbol = 'USDe';

UPDATE cda_issuer_registry SET disclosure_type = 'overcollateralized',
  expected_fields = '["collateral_ratio","total_supply","total_collateral_usd","vault_count","liquidation_threshold","collateral_types"]'::jsonb,
  verification_rules = '[{"rule":"collateral_ratio_gte_1","description":"Collateral ratio >= 1.0","severity":"critical"}]'::jsonb
WHERE asset_symbol IN ('DAI');

UPDATE cda_issuer_registry SET disclosure_type = 'algorithmic',
  expected_fields = '["collateral_ratio","total_supply","protocol_owned_liquidity","amo_balances","collateral_types"]'::jsonb,
  verification_rules = '[]'::jsonb
WHERE asset_symbol IN ('FRAX');

UPDATE cda_issuer_registry SET disclosure_type = 'rwa-tokenized',
  expected_fields = '["nav_per_token","total_supply","total_assets_usd","underlying_holdings","attestation_date","auditor_name","yield_rate"]'::jsonb,
  verification_rules = '[{"rule":"nav_positive","description":"NAV per token > 0","severity":"critical"}]'::jsonb
WHERE asset_symbol IN ('USDY');

INSERT INTO migrations (name) VALUES ('028_cda_disclosure_types') ON CONFLICT DO NOTHING;

COMMIT;
