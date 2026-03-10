# Basis Protocol — Stablecoin Integrity Index (SII)

## Overview
Comprehensive stablecoin risk analysis platform that calculates SII scores by collecting data from multiple sources (CoinGecko, DeFiLlama, Curve, Etherscan), crawls DeFi governance forums for intelligence, and provides a REST API for accessing risk scores and generating content opportunities.

## Architecture
- **Runtime**: Python 3.11 + Node.js 20
- **Backend**: FastAPI with Uvicorn
- **Frontend**: React 18 + Vite (built to frontend/dist, served by FastAPI)
- **Database**: PostgreSQL (Replit built-in)
- **Port**: 5000 (serves both dashboard and API)

## Project Structure
```
main.py                     - Entry point (API + background worker)
app/
  server.py                 - FastAPI routes + static file serving
  database.py               - PostgreSQL connection pool (contextmanager-based)
  config.py                 - Stablecoin registry and environment config
  scoring.py                - SII formula, weights, normalization
  governance.py             - Governance forum crawler + analysis
  content_engine.py         - Content opportunity generation
  worker.py                 - Background scoring cycle
  collectors/
    coingecko.py            - CoinGecko API collector
    defillama.py            - DeFiLlama collector
    curve.py                - Curve Finance collector
    etherscan.py            - Etherscan holder distribution collector
    offline.py              - Static/config-based components
frontend/
  src/App.jsx               - React dashboard (rankings, detail, methodology)
  src/main.jsx              - React entry point
  index.html                - HTML template
  vite.config.js            - Vite build config
  package.json              - Frontend dependencies
  dist/                     - Built output (served by FastAPI at root)
migrations/
  001_initial_schema.sql    - Core database schema (8 tables + governance)
exports/
  governance_export.sql     - Pre-imported governance data (113 docs, 24k+ mentions)
import_governance.py        - Governance data import utility
```

## Frontend Build
```bash
cd frontend && npx vite build
```
The built output in `frontend/dist/` is served by FastAPI at the root URL.
API endpoints remain at `/api/*`. No CORS issues since same domain.

## Database Tables
- `stablecoins` - Registry of 10 tracked stablecoins
- `component_readings` - Raw data points from collectors
- `scores` - Current computed SII scores
- `score_history` - Daily snapshots
- `score_events` - Crisis events timeline
- `historical_prices` - Hourly price data
- `deviation_events` - Detected peg deviations
- `data_provenance` - Audit trail
- `gov_documents` - Governance forum posts
- `gov_stablecoin_mentions` - Stablecoin mentions in governance
- `gov_metric_mentions` - Risk metric mentions
- `gov_analysis_tags` - Analysis tags
- `gov_crawl_logs` - Crawl history

## Key API Endpoints
- `GET /api/health` - System health
- `GET /api/scores` - All stablecoin scores
- `GET /api/scores/{coin}` - Detailed score
- `GET /api/scores/{coin}/history` - Historical scores
- `GET /api/compare?coins=usdc,usdt` - Compare stablecoins
- `GET /api/methodology` - Formula and weights
- `GET /api/governance/stats` - Governance intelligence
- `GET /api/governance/debates` - Hot debates
- `GET /api/governance/sentiment` - Sentiment trends
- `GET /api/content/opportunities` - Content opportunities

## Admin Endpoints (require ?key=ADMIN_KEY)
- `GET /admin` - Admin panel HTML page
- `GET /api/admin/health` - Enhanced system health with coverage, table sizes, crawl info
- `GET /api/admin/freshness` - Per-stablecoin data freshness by category
- `GET /api/admin/governance/stats` - Governance doc counts, mention breakdowns, sentiment
- `GET /api/admin/content/signals` - Hot governance topics matched to SII scores

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection (auto-configured)
- `COINGECKO_API_KEY` - Required for live scoring
- `ETHERSCAN_API_KEY` - Required for on-chain data
- `ANTHROPIC_API_KEY` - Optional, for content generation
- `ADMIN_KEY` - Required for admin panel access (/admin?key=...)
- `WORKER_ENABLED` - Set to "true" to enable background scoring
- `COLLECTION_INTERVAL` - Minutes between scoring cycles (default: 60)

## Workflow
Command: `python main.py`

## Recent Changes
- 2026-03-10: Complete frontend redesign — "regulatory disclosure document" aesthetic
  - Replaced dark theme with warm off-white (#f5f2ec) paper background
  - Typography: IBM Plex Mono (numbers/scores) + IBM Plex Sans (prose/headers)
  - Document block with 3px solid border and offset shadow
  - Three-section page header: title bar, formula bar, on-chain commit banner (decorative)
  - Redesigned table: columns are #, Stablecoin, SII Grade, Trend, Peg, Liq, Flow, Dist, Str
  - Score number inline with symbol name, large grade letters, sub-score bars (floor=50)
  - Hover-reveal detail strip: Price, Mkt Cap, Vol 24h, Reserve Type, Attestation, Chains, MiCA
  - Sparklines from 21-day history (skip if <5 points), gray for flat trends
  - Tier separator between A-tier and B-tier rows
  - Footnotes section: Component Weights, Grade Scale, Disclosure
  - Hardcoded MiCA status and Reserve Type per coin
  - Backup at frontend/src/App.jsx.backup
- 2026-03-10: Added USD1 (World Liberty Financial) as 10th stablecoin
  - CoinGecko ID: usd1-wlfi, contract: 0x8d0D000Ee44948FC98c9B98A4FA4921476f08B0d
  - BitGo Trust Company attestation (tier 2), monthly frequency
  - Reserve profile: 100% backed, 90% cash, 85% T-bills
  - First score: 83.36 (A-) with 42 components
  - Updated config.py, etherscan.py, offline.py, migrations
- 2026-02-11: Added admin panel and admin API endpoints
  - /api/admin/health, /api/admin/freshness, /api/admin/governance/stats, /api/admin/content/signals
  - /admin HTML page with dark theme: health, freshness, governance, content signals
  - ADMIN_KEY query parameter authentication on all admin routes
- 2026-02-11: Added React frontend dashboard
  - Vite + React 18 SPA served from root URL by FastAPI
  - Rankings table, detail view with score history chart, methodology page
  - API URL set to relative (same domain, no CORS)
  - Static assets mounted at /assets/, SPA catch-all for client routing
- 2026-02-11: Etherscan holder distribution collector
  - Queries 37 labeled known addresses (exchanges, DeFi, bridges, treasuries)
  - Distribution scores populated for all 9 stablecoins
- 2026-02-10: Initial deployment to Replit
  - Fixed governance.py get_conn() context manager bugs
  - Updated port from 8000 to 5000
  - Fixed migration schema (immutable date function for unique index)
  - Imported governance data (113 docs, 24k metric mentions)
  - Fixed health_check return value handling in main.py
