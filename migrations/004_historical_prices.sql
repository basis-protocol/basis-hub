-- Migration 004: Create legacy_historical_prices table for historical price data import
-- Source: historical_prices.sql (~185k rows of hourly stablecoin price data)

CREATE TABLE IF NOT EXISTS legacy_historical_prices (
    id INTEGER PRIMARY KEY,
    coingecko_id VARCHAR(100),
    "timestamp" TIMESTAMPTZ,
    price NUMERIC(20,8),
    market_cap NUMERIC(20,2),
    volume_24h NUMERIC(20,2),
    created_at TIMESTAMPTZ
);

INSERT INTO migrations (name, applied_at) VALUES ('004_historical_prices', NOW()) ON CONFLICT DO NOTHING;
