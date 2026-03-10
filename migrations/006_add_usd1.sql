INSERT INTO stablecoins (id, name, symbol, issuer, coingecko_id, contract, decimals, scoring_enabled, attestation_config, regulatory_licenses)
VALUES
    ('usd1', 'World Liberty Financial USD', 'USD1', 'World Liberty Financial', 'usd1-wlfi', '0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d', 18, TRUE,
     '{"auditor": "BitGo Trust Company", "frequency": "monthly", "frequency_days": 35, "transparency_url": "https://worldlibertyfinancial.com/usd1"}'::jsonb,
     ARRAY[]::TEXT[])
ON CONFLICT (id) DO NOTHING;

INSERT INTO migrations (name) VALUES ('006_add_usd1') ON CONFLICT DO NOTHING;
