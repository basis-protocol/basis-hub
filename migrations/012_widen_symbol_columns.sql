-- Migration 012: Widen VARCHAR(20) symbol columns to VARCHAR(50)
-- ERC-20 token symbols are arbitrary-length strings. LP tokens, meme tokens,
-- and governance tokens frequently exceed 20 characters (e.g. "UNI-V2-USDC-ETH",
-- "sAMMV2-USDC/FRAX", etc.), causing StringDataRightTruncation errors during
-- wallet indexer pipeline runs. Widen all three affected columns to VARCHAR(50).

ALTER TABLE wallet_graph.wallet_holdings
    ALTER COLUMN symbol TYPE VARCHAR(50);

ALTER TABLE wallet_graph.wallet_risk_scores
    ALTER COLUMN dominant_asset TYPE VARCHAR(50);

ALTER TABLE wallet_graph.unscored_assets
    ALTER COLUMN symbol TYPE VARCHAR(50);

-- Track migration
INSERT INTO migrations (name) VALUES ('012_widen_symbol_columns') ON CONFLICT DO NOTHING;
