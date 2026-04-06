-- Migration 037: x402 payment logging
-- Date: 2026-04-06

CREATE TABLE IF NOT EXISTS payment_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    endpoint TEXT NOT NULL,
    price_usd DECIMAL(10, 6) NOT NULL,
    protocol TEXT NOT NULL DEFAULT 'x402',
    payer_address TEXT,
    tx_hash TEXT,
    verified BOOLEAN DEFAULT FALSE,
    ip_address TEXT
);

CREATE INDEX IF NOT EXISTS idx_payment_log_ts ON payment_log (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_payment_log_payer ON payment_log (payer_address);
