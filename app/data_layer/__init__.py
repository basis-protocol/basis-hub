"""
Universal Risk Data Layer
=========================
Collects and normalizes the periodic table of on-chain risk data.
Each tier is a self-contained collector that:
  - Fetches from external APIs using the shared rate limiter
  - Validates incoming data via coherence guards
  - Stores to its own table with integrity domain
  - Tracks API usage via the centralized tracker

Tiers:
  1. Per-Asset Liquidity Depth (GeckoTerminal + CoinGecko tickers)
  2. Yield and Rate Data (DeFiLlama yields)
  3. Governance Activity (Snapshot + Tally expansion)
  4. Bridge Flow Volumes (DeFiLlama bridges)
  5. Exchange-Level Data (CoinGecko exchanges + Etherscan)
  6. Cross-Entity Correlation (computed)
  7. Historical Volatility Surfaces (computed from price data)
  8. Structured Incident History (computed from discovery signals)
"""
