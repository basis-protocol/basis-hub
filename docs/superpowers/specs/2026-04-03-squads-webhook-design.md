# Squads Webhook — Basis Score Overlay for Drift

**Date:** 2026-04-03
**Status:** Design approved, pending implementation
**Context:** Option C from docs/SQUADS_GUARD_SPEC.md — advisory webhook, not blocking

## Summary

A FastAPI service that receives Squads multisig transaction proposals via webhook, scores all stablecoins and protocols involved using the live Basis API (SII + PSI), computes CQI where both scores exist, and returns a formatted risk assessment. Advisory only — informs multisig signers, does not block execution.

## Architecture

Standalone module in `squads-guard/` that can run independently (port 8081) or be mounted into the hub as an APIRouter at `/api/squads/*`.

```
squads-guard/
├── main.py          # Standalone entry point (uvicorn, port 8081)
├── router.py        # APIRouter with all endpoints (importable by hub)
├── scorer.py        # Score fetching + CQI computation
├── extractor.py     # Parse Squads payloads, extract mints/programs
├── formatter.py     # Build assessment response
├── config.py        # Stablecoin mints, protocol programs, grade mappings
└── requirements.txt # fastapi, uvicorn, httpx
```

**Deployment modes:**
- **Standalone:** `python squads-guard/main.py` — runs on port 8081
- **Hub-mounted:** Import `router` from `squads-guard/router.py`, mount at `/api/squads` in `app/server.py`

## Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/webhook` | POST | Receive Squads transaction proposal, score it, return assessment |
| `/score` | POST | Manual scoring — `{"stablecoins": ["usdc"], "protocols": ["drift"]}` |
| `/demo/drift` | GET | Hardcoded USDC/USDT + Drift demo |
| `/health` | GET | Service health check |

## Data Flow

### Webhook flow
1. Squads POSTs proposal payload to `/webhook`
2. `extractor.py` parses instructions from multiple possible payload shapes (`body.instructions`, `body.message.instructions`, `body.transaction.message.instructions`)
3. Scans all account pubkeys and program IDs against known stablecoin mints and protocol programs in `config.py`
4. `scorer.py` fetches SII via `GET /api/scores/{coin}` and PSI via `GET /api/psi/scores/{slug}` in parallel using `httpx.AsyncClient`
5. Computes CQI = `sqrt(SII * PSI)` on 0-100 scale when both scores exist
6. `formatter.py` builds structured response with status, text summary, warnings, and raw scores

### Graceful degradation
- No stablecoins found: empty stablecoin section
- PSI returns 404: SII-only assessment, no CQI
- Neither found: `no_data` status with empty assessment frame
- API fetch failure: that score treated as absent, not an error

## Config

### Stablecoin mints (Solana)
| Mint address | Basis ID |
|---|---|
| `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` | usdc |
| `Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB` | usdt |
| `EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm` | dai |
| `2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo` | pyusd |

### Protocol programs (Solana)
| Program ID | Basis slug |
|---|---|
| `dRiftyHA39MWEi3m9aunc5MzRF1JYuBsbn6VPcn33UH` | drift |
| `JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4` | jupiter-perpetual-exchange |
| `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | raydium |

### Grade emoji mapping
A+/A/A- = green, B+/B/B- = yellow, C+/C/C- = orange, D+/D/D- = red, F = stop

## Scoring Logic

- **SII source:** `GET {BASIS_API_URL}/api/scores/{coin_id}` — returns score (0-100), grade
- **PSI source:** `GET {BASIS_API_URL}/api/psi/scores/{slug}` — returns score (0-100), grade
- **CQI formula:** `sqrt(sii_score * psi_score)` on 0-100 scale, same as on-chain oracle
- **Grade bands:** A+ >= 90, A >= 85, A- >= 80, B+ >= 75, B >= 70, B- >= 65, C+ >= 60, C >= 55, C- >= 50, D+ >= 45, D >= 40, D- >= 35, F < 35

## Warning Triggers

- SII below 60 for any stablecoin
- PSI below 50 for any protocol
- CQI more than 15 points below SII (protocol risk significantly reducing stablecoin quality)

## Response Format

```json
{
  "status": "pass|caution|warning|no_data",
  "summary": "━━━ Basis Protocol Risk Assessment ━━━\n...",
  "warnings": ["..."],
  "scores": {
    "stablecoins": {"usdc": 88.6},
    "protocols": {"drift": 74.0},
    "cqi": {"USDC × Drift": 80.9}
  },
  "scored_at": "2026-04-03T12:00:00Z",
  "source": "https://basisprotocol.xyz"
}
```

**Status thresholds:**
- `warning`: any score below 50
- `caution`: any score below 65
- `pass`: all scores 65+
- `no_data`: no scores available

## Security

- No authentication on the webhook (advisory service, read-only Basis API calls)
- No secrets stored — only needs `BASIS_API_URL` env var
- 10-second timeout on all outbound API calls

## Not in scope

- Blocking transactions (this is advisory only)
- On-chain oracle reads (uses HTTP API)
- Solana toolchain / Anchor SDK
- Persisting webhook history to database
- Auth/API keys (can be added later)

## Dependencies

- Basis hub API (live at basisprotocol.xyz)
- Python: fastapi, uvicorn, httpx
- No new dependencies for the hub if mounted as router
