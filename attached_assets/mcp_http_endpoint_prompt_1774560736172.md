# Add MCP HTTP Endpoint to Hub Server

## What & Why

The Basis MCP server is published on npm (`@basis-protocol/mcp-server`) and the official MCP Registry. Some MCP registries (Smithery) and some MCP clients require a hosted HTTP endpoint rather than an npm stdio package. Adding an `/mcp` route to the hub lets agents connect over HTTP without installing anything.

The MCP server logic already exists in the `basis-mcp` repo as TypeScript. We are NOT porting that code. Instead, we're building a lightweight Python MCP endpoint directly in the hub using the `mcp` Python SDK that exposes the same 8 tools by calling our own API internally (localhost).

## Done looks like

* `POST /mcp`, `GET /mcp`, `DELETE /mcp` routes exist on the hub and handle MCP streamable-http transport
* An MCP client connecting to `https://basis-deploy-guide.replit.app/mcp` can list tools and call them
* All 8 tools work: `get_stablecoin_scores`, `get_stablecoin_detail`, `get_wallet_risk`, `get_wallet_holdings`, `get_riskiest_wallets`, `get_scoring_backlog`, `check_transaction_risk`, `get_methodology`
* Each tool calls the hub's own API endpoints internally (localhost, not external HTTP) to get data
* The existing API endpoints are not modified in any way

## Out of scope

* Changing any existing API endpoints
* Touching the scoring engine, indexer, or database schema
* Authentication on the MCP endpoint (open for now, same as the REST API)
* SSE transport (streamable-http only)

## Architecture

The MCP endpoint is a thin adapter layer:

```
MCP Client → POST /mcp → MCP SDK handler → tool call → internal API call → response
```

Each tool is a wrapper that calls the existing FastAPI endpoints internally. For example, `get_stablecoin_scores` calls `GET /api/scores` on localhost and reformats the response. This means the MCP tools always return exactly the same data as the REST API — no duplication, no drift.

## Tasks

### 1. Install the MCP Python SDK

Add `mcp[http]` to requirements. The package is `mcp` on PyPI (the official Anthropic MCP SDK for Python).

```bash
pip install mcp[http] --break-system-packages
```

Add `mcp[http]` to `requirements.txt` or `pyproject.toml`.

### 2. Create `app/mcp_server.py`

This file defines the MCP server with all 8 tools. Each tool fetches data from the hub's own API using `httpx` against `http://localhost:{PORT}`.

```python
"""
Basis Protocol — MCP Server (HTTP transport)
=============================================
Thin adapter: exposes 8 MCP tools that call the hub's REST API internally.
"""

import os
import json
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="basis-protocol",
    version="1.0.3",
    description="Verifiable risk intelligence for on-chain finance.",
)

API_BASE = f"http://localhost:{os.environ.get('PORT', '8080')}"


async def _api_get(path: str) -> dict:
    """Call a hub API endpoint internally."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{API_BASE}{path}", timeout=15.0)
        if resp.status_code == 404:
            return {"error": "not_found"}
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def get_stablecoin_scores(min_grade: str = None, sort_by: str = "score_desc") -> str:
    """Get current SII scores for all scored stablecoins. Use before any decision involving stablecoins."""
    data = await _api_get("/api/scores")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_stablecoin_detail(coin: str) -> str:
    """Full score breakdown for a specific stablecoin including category scores and methodology version."""
    data = await _api_get(f"/api/scores/{coin.lower()}")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_wallet_risk(address: str) -> str:
    """Get risk profile for a specific Ethereum wallet — composite risk score, concentration, coverage quality."""
    data = await _api_get(f"/api/wallets/{address.lower()}")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_wallet_holdings(address: str) -> str:
    """Detailed holdings breakdown for an Ethereum wallet with per-asset SII scores."""
    data = await _api_get(f"/api/wallets/{address.lower()}/holdings")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_riskiest_wallets(limit: int = 20) -> str:
    """Wallets with the most capital at risk — lowest risk scores weighted by total value."""
    data = await _api_get(f"/api/wallets/riskiest?limit={limit}")
    return json.dumps(data, indent=2)


@mcp.tool()
async def get_scoring_backlog(limit: int = 20) -> str:
    """Unscored stablecoin assets ranked by total capital exposure across all indexed wallets."""
    data = await _api_get(f"/api/backlog?limit={limit}")
    return json.dumps(data, indent=2)


@mcp.tool()
async def check_transaction_risk(from_address: str, to_address: str, asset_symbol: str) -> str:
    """Composite risk assessment for a stablecoin transaction — evaluates asset, sender, and receiver."""
    import asyncio
    asset_task = _api_get(f"/api/scores/{asset_symbol.lower()}")
    sender_task = _api_get(f"/api/wallets/{from_address.lower()}")
    receiver_task = _api_get(f"/api/wallets/{to_address.lower()}")
    asset, sender, receiver = await asyncio.gather(asset_task, sender_task, receiver_task)
    result = {
        "asset": asset,
        "sender": sender,
        "receiver": receiver,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    return json.dumps(result, indent=2)


@mcp.tool()
async def get_methodology() -> str:
    """Returns the current SII formula, category weights, grade scale, and version information."""
    data = await _api_get("/api/methodology")
    return json.dumps(data, indent=2)
```

### 3. Mount the MCP endpoint in `app/server.py`

In the startup event (after the existing route registrations), add:

```python
# MCP HTTP endpoint
try:
    from app.mcp_server import mcp as mcp_server
    from mcp.server.streamable_http import StreamableHTTPServerTransport
    
    @app.post("/mcp")
    @app.get("/mcp")
    @app.delete("/mcp")
    async def mcp_endpoint(request: Request):
        # Delegate to MCP SDK's streamable HTTP handler
        transport = StreamableHTTPServerTransport(session_id_generator=None)
        server = mcp_server._mcp_server  # Access the underlying Server instance
        await server.connect(transport)
        return await transport.handle_request(request)
    
    logger.info("MCP HTTP endpoint registered at /mcp")
except ImportError as e:
    logger.warning(f"MCP endpoint not available: {e}")
except Exception as e:
    logger.warning(f"MCP endpoint registration failed: {e}")
```

Note: The exact integration pattern depends on the `mcp` SDK version. The FastMCP library may have a built-in ASGI mount method. Check the SDK docs — if `mcp.asgi_app()` or `mcp.streamable_http_app()` exists, use that instead and mount it with `app.mount("/mcp", mcp_asgi_app)`.

### 4. Test

After deploying, verify with:

```bash
curl -X POST https://basis-deploy-guide.replit.app/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Should return all 8 tools.

## Relevant files

* `app/server.py` — mount the MCP endpoint
* `app/mcp_server.py` — new file, MCP tool definitions
* `requirements.txt` — add `mcp[http]`

## Do NOT

* Modify any existing API endpoints
* Change the database schema
* Touch the indexer or scoring engine
* Add authentication to the MCP endpoint
* Deploy automatically — let me review first
