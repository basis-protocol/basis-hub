# Wallet Risk Graph — V1 Spec

> This is the build spec for Claude Code. Read CLAUDE.md and STRATEGY.md first.
> This module lives at `app/indexer/`. It does NOT modify any existing SII code.

## What This Does

Indexes Ethereum mainnet wallets, profiles their stablecoin holdings, and computes a risk score for each wallet based on the SII scores of the assets it holds. The wallet is the universal join key — future risk surfaces (PSI, TTI, CVI) enrich the same graph.

## Database Schema (Migration 007)

Schema: `wallet_graph` (separate from public schema, same Neon Postgres instance)

```sql
CREATE SCHEMA IF NOT EXISTS wallet_graph;

-- 1. Indexed wallets
CREATE TABLE wallet_graph.wallets (
    address VARCHAR(42) PRIMARY KEY,          -- 0x-prefixed, checksummed
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_indexed_at TIMESTAMPTZ,
    total_stablecoin_value DOUBLE PRECISION,  -- USD total across all stablecoin holdings
    size_tier VARCHAR(20),                    -- 'whale', 'institutional', 'retail'
    source VARCHAR(50),                       -- how we discovered this wallet: 'top_holder_usdc', 'top_holder_usdt', etc.
    is_contract BOOLEAN DEFAULT FALSE,        -- multisig, treasury, protocol contract
    label VARCHAR(200),                       -- optional: 'Circle Treasury', 'Aave V3', etc.
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Wallet holdings (one row per wallet per token)
CREATE TABLE wallet_graph.wallet_holdings (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL REFERENCES wallet_graph.wallets(address),
    token_address VARCHAR(42) NOT NULL,       -- ERC-20 contract address
    symbol VARCHAR(20),
    balance DOUBLE PRECISION,                 -- raw token balance (adjusted for decimals)
    value_usd DOUBLE PRECISION,               -- balance × current price
    is_scored BOOLEAN DEFAULT FALSE,          -- do we have an SII score for this asset?
    sii_score DOUBLE PRECISION,               -- SII score at time of indexing (NULL if unscored)
    sii_grade VARCHAR(2),                     -- grade at time of indexing
    pct_of_wallet DOUBLE PRECISION,           -- this holding as % of wallet's total stablecoin value
    indexed_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(wallet_address, token_address, (indexed_at::date))
);

CREATE INDEX idx_holdings_wallet ON wallet_graph.wallet_holdings(wallet_address);
CREATE INDEX idx_holdings_token ON wallet_graph.wallet_holdings(token_address);
CREATE INDEX idx_holdings_indexed ON wallet_graph.wallet_holdings(indexed_at DESC);

-- 3. Wallet risk scores (one row per wallet per scoring run)
CREATE TABLE wallet_graph.wallet_risk_scores (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL REFERENCES wallet_graph.wallets(address),
    
    -- Core score
    risk_score DOUBLE PRECISION,              -- value-weighted avg SII (0-100)
    risk_grade VARCHAR(2),                    -- A+ through F
    
    -- Enrichment signals
    concentration_hhi DOUBLE PRECISION,       -- Herfindahl index (0-10000), normalized to 0-100 for display
    concentration_grade VARCHAR(2),           -- grade based on HHI
    unscored_pct DOUBLE PRECISION,            -- % of stablecoin value in unscored assets
    coverage_quality VARCHAR(20),             -- 'full', 'high', 'partial', 'low' based on unscored_pct
    
    -- Composition summary
    num_scored_holdings INTEGER,
    num_unscored_holdings INTEGER,
    num_total_holdings INTEGER,
    dominant_asset VARCHAR(20),               -- symbol of largest holding
    dominant_asset_pct DOUBLE PRECISION,      -- % of wallet in dominant asset
    
    -- Metadata
    total_stablecoin_value DOUBLE PRECISION,
    size_tier VARCHAR(20),
    formula_version VARCHAR(20) DEFAULT 'wallet-v1.0.0',
    computed_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(wallet_address, (computed_at::date))
);

CREATE INDEX idx_wrs_wallet ON wallet_graph.wallet_risk_scores(wallet_address);
CREATE INDEX idx_wrs_score ON wallet_graph.wallet_risk_scores(risk_score DESC);
CREATE INDEX idx_wrs_computed ON wallet_graph.wallet_risk_scores(computed_at DESC);

-- 4. Unscored stablecoin backlog
CREATE TABLE wallet_graph.unscored_assets (
    token_address VARCHAR(42) PRIMARY KEY,
    symbol VARCHAR(20),
    name VARCHAR(100),
    decimals INTEGER,
    coingecko_id VARCHAR(100),                -- NULL until mapped
    
    -- Demand signals (updated each indexing run)
    wallets_holding INTEGER DEFAULT 0,        -- how many indexed wallets hold this
    total_value_held DOUBLE PRECISION DEFAULT 0, -- total USD across all indexed wallets
    avg_holding_value DOUBLE PRECISION DEFAULT 0,
    max_single_holding DOUBLE PRECISION DEFAULT 0,
    
    -- Scoring pipeline status
    scoring_status VARCHAR(20) DEFAULT 'unscored', -- 'unscored', 'queued', 'in_progress', 'scored'
    scoring_priority INTEGER,                 -- computed: rank by total_value_held
    notes TEXT,                               -- manual notes: "no coingecko listing", "algorithmic", etc.
    
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_unscored_priority ON wallet_graph.unscored_assets(total_value_held DESC);
CREATE INDEX idx_unscored_status ON wallet_graph.unscored_assets(scoring_status);
```

## Size Tier Thresholds

| Tier | Total Stablecoin Value |
|------|----------------------|
| whale | >= $10M |
| institutional | >= $100K |
| retail | < $100K |

## Coverage Quality Thresholds

| Quality | Unscored % |
|---------|-----------|
| full | 0% |
| high | < 10% |
| partial | 10-40% |
| low | > 40% |

## Scoring Formulas

### Wallet Risk Score (wallet-v1.0.0)

```python
# Only scored holdings contribute to the risk score
scored_holdings = [h for h in holdings if h.is_scored and h.sii_score is not None]

if not scored_holdings:
    risk_score = None  # cannot score — 100% unscored exposure

total_scored_value = sum(h.value_usd for h in scored_holdings)
risk_score = sum(h.value_usd * h.sii_score for h in scored_holdings) / total_scored_value
```

### Concentration HHI

```python
# Herfindahl-Hirschman Index across ALL stablecoin holdings (scored + unscored)
total_value = sum(h.value_usd for h in all_holdings)
shares = [(h.value_usd / total_value) * 100 for h in all_holdings]
hhi = sum(s ** 2 for s in shares)
# HHI range: 10000 (single asset) to 10000/N (equally split across N assets)
# Normalize: hhi_normalized = 100 - ((hhi / 10000) * 100) so higher = more diversified
```

### Unscored Exposure

```python
total_value = sum(h.value_usd for h in all_holdings)
unscored_value = sum(h.value_usd for h in all_holdings if not h.is_scored)
unscored_pct = (unscored_value / total_value) * 100 if total_value > 0 else 0
```

## Module Structure

```
app/indexer/
├── __init__.py
├── config.py          # known stablecoin contracts (scored + common unscored)
├── scanner.py         # Etherscan API: fetch token balances for an address
├── scorer.py          # compute wallet risk score, HHI, coverage
├── pipeline.py        # orchestrator: seed wallets → scan → score → store
├── backlog.py         # unscored asset tracking and priority computation
└── api.py             # FastAPI routes for /api/wallets/*
```

## Pipeline Flow

```
1. SEED
   - Query existing component_readings for top holder data (Etherscan collector)
   - OR: directly call Etherscan "top token holders" for each of 10 scored stablecoins
   - Take top 1000 per coin → deduplicate → ~3000-5000 unique wallets

2. SCAN (for each wallet)
   - Etherscan API: get all ERC-20 token balances
   - Filter to known stablecoin contracts (scored + common unscored list)
   - For each stablecoin held:
     - Look up current SII score from scores table (if scored)
     - Look up current price from CoinGecko data (if available)
     - Compute value_usd = balance × price
   - Rate limit: respect Etherscan API limits (5 calls/sec on free tier)

3. SCORE (for each wallet)
   - Compute risk_score (value-weighted SII average)
   - Compute concentration_hhi
   - Compute unscored_pct and coverage_quality
   - Determine size_tier from total_stablecoin_value
   - Determine dominant_asset

4. STORE
   - Upsert wallet_graph.wallets
   - Insert wallet_graph.wallet_holdings (daily snapshots)
   - Insert wallet_graph.wallet_risk_scores (daily snapshots)
   - Upsert wallet_graph.unscored_assets with updated demand signals

5. BACKLOG UPDATE
   - For all unscored assets seen this run:
     - Count wallets_holding
     - Sum total_value_held
     - Compute scoring_priority = rank by total_value_held DESC
   - This produces a prioritized queue: "score GHO next ($47M across 200 wallets)"
```

## Known Stablecoin Contracts (config.py seed list)

### Scored (SII exists — from app/config.py STABLECOIN_REGISTRY)
- USDC: 0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48
- USDT: 0xdac17f958d2ee523a2206206994597c13d831ec7
- DAI: 0x6b175474e89094c44da98b954eedeac495271d0f
- FRAX: 0x853d955acef822db058eb8505911ed77f175b99e
- PYUSD: 0x6c3ea9036406852006290770bedfcaba0e23a0e8
- FDUSD: 0xc5f0f7b66764F6ec8C8Dff7BA683102295E16409
- TUSD: 0x0000000000085d4780B73119b644AE5ecd22b376
- USDD: 0x0C10bF8FcB7Bf5412187A595ab97a3609160b5c6
- USDe: 0x4c9EDD5852cd905f086C759E8383e09bff1E68B3
- USD1: 0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d

### Unscored (common, track in backlog)
- GHO (Aave): 0x40D16FC0246aD3160Ccc09B8D0D3A2cD28aE6C2f
- crvUSD (Curve): 0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E
- LUSD (Liquity): 0x5f98805A4E8be255a32880FDeC7F6728C6568bA0
- sUSD (Synthetix): 0x57Ab1ec28D129707052df4dF418D58a2D46d5f51
- DOLA (Inverse): 0x865377367054516e17014CcdED1e7d814EDC9ce4
- MIM (Abracadabra): 0x99D8a9C45b2ecA8864373A26D1459e3Dff1e17F3
- EURS (Stasis): 0xdB25f211AB05b1c97D595516F45D248390d6bfa5
- USDP (Paxos): 0x8E870D67F660D95d5be530380D0eC0bd388289E1
- GUSD (Gemini): 0x056Fd409E1d7A124BD7017459dFEa2F387b6d5Cd
- RAI (Reflexer): 0x03ab458634910AaD20eF5f1C8ee96F1D6ac54919

This list will grow. Any stablecoin-like ERC-20 seen during scanning that isn't in either list gets added to unscored_assets automatically.

## API Endpoints (registered on app at startup, like governance routes)

```
GET /api/wallets/{address}
    → wallet profile: risk score, grade, holdings breakdown, concentration, coverage

GET /api/wallets/{address}/history
    → daily risk score history for a wallet

GET /api/wallets/top
    → top wallets by stablecoin value, filterable by size_tier

GET /api/wallets/riskiest
    → wallets with lowest risk scores (most at-risk capital)

GET /api/wallets/stats
    → aggregate: total wallets indexed, total value tracked, coverage stats

GET /api/backlog
    → unscored asset backlog, sorted by priority (total_value_held DESC)

GET /api/backlog/{token_address}
    → detail for one unscored asset: which wallets hold it, how much
```

## Scheduling

- Runs daily, after the SII scoring cycle completes (so it uses fresh SII scores)
- Can also be triggered manually via admin endpoint: `POST /api/admin/index-wallets?key=ADMIN_KEY`
- First run: seed + scan + score (~3000-5000 wallets × Etherscan calls, ~1 hour)
- Subsequent runs: re-scan existing wallets + add new ones discovered via holder lists

## Cost Estimate

- Etherscan API: Lite plan = 5 calls/sec, 100K calls/day. ~20K calls per full run (seed + scan). Under 20% of daily limit.
- Full indexing run takes ~1 hour at 5 calls/sec.
- Neon Postgres: wallet_graph schema adds maybe 100K-1M rows over time. Well within free/starter tier.
- Total incremental cost: $49/mo Etherscan at V1 scale. Grows to ~$500/mo at 100K+ wallets.

## Success Metrics (from STRATEGY.md proof discipline)

- Wallets indexed (target: 3000-5000 unique in week 1)
- External lookups on /api/wallets/ endpoints (adoption signal)
- Unscored backlog generating clear "score this next" priorities
- Risk score distribution making intuitive sense (USDC-heavy wallets score high, TUSD-heavy lower)

## What This Does NOT Do (V1)

- Multi-chain (Ethereum mainnet only)
- Non-stablecoin tokens (future: PSI-scored protocols, TTI-scored treasuries)
- On-chain publication (future: oracle writes wallet risk scores to Base/Arbitrum)
- Real-time indexing (daily batch is fine for V1)
- Wallet labeling/identity (basic label field exists, but no ENS resolution or Arkham-style intelligence)
