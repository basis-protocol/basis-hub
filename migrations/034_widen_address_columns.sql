-- Migration 034: Widen wallet_graph address columns from VARCHAR(42) to VARCHAR(128)
-- VARCHAR(42) was sized for EVM addresses only; Solana base58 addresses are 44 chars.
-- Widening to 128 safely covers both chains and any future additions.

ALTER TABLE wallet_graph.wallets ALTER COLUMN address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_edges ALTER COLUMN from_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_edges ALTER COLUMN to_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_edges_archive ALTER COLUMN from_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_edges_archive ALTER COLUMN to_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.edge_build_status ALTER COLUMN wallet_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_holdings ALTER COLUMN wallet_address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_profiles ALTER COLUMN address TYPE VARCHAR(128);
ALTER TABLE wallet_graph.wallet_risk_scores ALTER COLUMN wallet_address TYPE VARCHAR(128);
