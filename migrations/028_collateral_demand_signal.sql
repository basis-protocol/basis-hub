-- Migration 028: Add collateral demand signals to unscored_assets
-- Connects the collateral exposure pipeline to the auto-promote backlog

ALTER TABLE wallet_graph.unscored_assets
ADD COLUMN IF NOT EXISTS protocol_collateral_tvl DOUBLE PRECISION DEFAULT 0;

ALTER TABLE wallet_graph.unscored_assets
ADD COLUMN IF NOT EXISTS protocol_count INTEGER DEFAULT 0;
