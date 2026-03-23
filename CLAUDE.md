# Basis Protocol — Claude Code Context

## What This Project Is

Basis Protocol is decision integrity infrastructure for on-chain finance. The wedge product is the **Stablecoin Integrity Index (SII)** — a deterministic, versioned scoring system for stablecoin risk. The V4 evolution adds a **Wallet Risk Graph**: every wallet gets a risk profile based on the assets it holds.

## What's Running (DO NOT BREAK)

The SII dashboard and API are **live in production** at this Replit deployment. The following are stable and should not be modified without explicit instruction:

- `main.py` — Entry point. Runs uvicorn + background worker thread on port 5000.
- `app/server.py` — FastAPI server with 18+ API endpoints. Serves React SPA.
- `app/scoring.py` — SII v1.0.0 formula. Canonical weights. Do not change without versioning.
- `app/worker.py` — Hourly scoring cycle across 10 stablecoins. Runs in daemon thread.
- `app/collectors/` — Data collectors (CoinGecko, DeFiLlama, Curve, Etherscan, offline).
- `app/config.py` — Stablecoin registry (10 coins: USDC, USDT, DAI, FRAX, PYUSD, FDUSD, TUSD, USDD, USDe, USD1).
- `app/database.py` — Neon Postgres connection pool (psycopg2).
- `app/governance.py` — Governance document crawler + sentiment analysis.
- `app/content_engine.py` — Content signal generation from governance data.
- `frontend/src/App.jsx` — React dashboard (single-file, 47KB). Vite build.
- `migrations/` — Applied schema. 8 core tables: stablecoins, component_readings, scores, score_history, score_events, historical_prices, deviation_events, data_provenance.

## Architecture

```
main.py (uvicorn + worker thread)
├── app/server.py (FastAPI — serves API + React SPA)
│   ├── /api/health, /api/scores, /api/scores/{coin}
│   ├── /api/history/{coin}, /api/methodology
│   ├── /api/admin/* (key-protected)
│   └── governance + content routes (registered at startup)
├── app/worker.py (background scoring cycle)
│   ├── collectors/ → component_readings table
│   ├── scoring.py → scores table
│   └── store_history_snapshot → score_history table
├── app/database.py (Neon Postgres pool)
└── frontend/dist/ (pre-built React app)
```

## Database (Neon Postgres)

Tables: stablecoins, component_readings, scores, score_history, score_events, historical_prices, deviation_events, data_provenance, migrations, governance_documents, governance_stablecoin_mentions, governance_metric_mentions.

Connection via `DATABASE_URL` env var. Pool: min=2, max=10.

## Environment Variables

- `DATABASE_URL` — Neon Postgres connection string
- `COINGECKO_API_KEY` — CoinGecko Pro API
- `ETHERSCAN_API_KEY` — Etherscan API
- `ALCHEMY_API_KEY` — Alchemy (optional)
- `ADMIN_KEY` — Admin panel access
- `WORKER_ENABLED` — true/false for background scoring
- `COLLECTION_INTERVAL` — minutes between scoring cycles (default: 60)
- `PORT` / `API_PORT` — server port (default: 5000)

## SII Formula (v1.0.0 — canonical, do not modify)

```
SII = 0.30×Peg + 0.25×Liquidity + 0.15×MintBurn + 0.10×Distribution + 0.20×Structural

Structural = 0.30×Reserves + 0.20×SmartContract + 0.15×Oracle + 0.20×Governance + 0.15×Network
```

## What To Build (V4 Priorities)

New work goes in NEW files/modules. Do not modify existing stable code unless fixing a bug.

### 1. Wallet Risk Graph (top priority)
- New module: `app/indexer/` — wallet indexing and risk graph construction
- New tables: `wallets`, `wallet_holdings`, `wallet_risk_scores`
- New API routes: `/api/wallets/{address}`, `/api/wallets/{address}/risk`
- Reads from: Etherscan/Alchemy APIs, existing SII scores
- The wallet is the universal join key — every address gets a risk profile based on asset holdings

### 2. Distribution Channels (bots, integrations)
- Twitter/X bot, Telegram bot, Discord bot — thin wrappers around the existing API
- MCP server for agent framework listings
- MetaMask Snap, Safe Guard Module

### 3. On-Chain Infrastructure
- Oracle contract deployment (Base/Arbitrum)
- Keeper script for oracle updates

## Conventions

- Python backend (FastAPI, psycopg2, httpx for async HTTP)
- React frontend (Vite, single-file App.jsx pattern)
- All database access through `app/database.py` helpers (fetch_one, fetch_all, execute, get_cursor)
- New migrations go in `migrations/` with sequential numbering (next: 007)
- Scores are 0-100, grades A+ through F
- Never use the word "rating" — use "score," "index," "surface"
- All new API routes under `/api/` prefix
- CORS is open (`*`) for now

## Git

- Remote: https://github.com/shlok-lgtm/Deploy-Guide (public)
- Branch: main
- Push regularly. Large SQL files are in .gitignore.

## Do NOT

- Restart the running server (it's serving production traffic)
- Modify scoring weights without explicit instruction and version bump
- Delete or restructure existing database tables
- Rewrite App.jsx from scratch (it's 47KB and working)
- Install heavy dependencies without asking first
- Use `sudo` for anything
