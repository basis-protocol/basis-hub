## LLL Phase 1 — Scoping Document

### Budget Inventory

| Provider | Daily budget | Current usage (est.) | Headroom |
|---|---|---|---|
| Blockscout v2 | 100K credits/day | ~2K (scanner + edges) | ~98K |
| Etherscan | 200K calls/day | ~50K (edges, mint/burn, contracts) | ~150K |
| Alchemy | 1M CU/day (30M/mo free) | ~50K (oracle reads, 6 feeds × hourly) | ~950K |
| CoinGecko | 16.6K/day | ~14K (entity snapshots, peg, OHLCV) | ~2.6K |

### Pipeline 1: Protocol Transaction Traces

**Source:** Blockscout `GET /api/v2/transactions/{hash}/raw-trace`
**Scope:** 10 tx per PSI protocol per day × 13 protocols = **130 calls/day**
**Budget impact:** 130 / 100K = **0.13%** of Blockscout daily budget

**Migration:** `090_protocol_trace_observations.sql`
```sql
CREATE TABLE IF NOT EXISTS protocol_trace_observations (
    id BIGSERIAL PRIMARY KEY,
    tx_hash TEXT NOT NULL,
    protocol_slug TEXT NOT NULL,
    chain TEXT NOT NULL DEFAULT 'ethereum',
    block_number BIGINT,
    from_address TEXT,
    to_address TEXT,
    value_eth NUMERIC,
    trace_json JSONB,
    call_depth_max INTEGER,
    internal_tx_count INTEGER,
    content_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tx_hash, protocol_slug)
);

CREATE INDEX IF NOT EXISTS idx_proto_trace_slug ON protocol_trace_observations(protocol_slug, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proto_trace_chain ON protocol_trace_observations(chain, created_at DESC);
```

**Collector:** `app/data_layer/protocol_trace_collector.py`

**Data flow:**
1. Query `rpi_protocol_config` for active protocol slugs
2. For each protocol, find the protocol's contract addresses from `protocol_pool_wallets` or `rpi_protocol_config`
3. Hit Blockscout `GET /api/v2/addresses/{address}/transactions?filter=to` for recent txs (1 call per protocol)
4. Pick top 10 by value, fetch raw trace for each (10 calls per protocol)
5. Store trace_json, extract call_depth_max and internal_tx_count as derived columns
6. Compute content_hash over (tx_hash, protocol_slug, trace_json)

**Integration:** Enrichment worker, daily gate (`min_hours=24`), group `"data_layer"`, priority 4

**Attestation:** `attest_data_batch("protocol_traces", records)` — content_hash is SHA-256 of `(tx_hash || protocol_slug || trace_json_canonical)`

**Kill-signal:** If >20% of trace fetches return 429 or 5xx in a single run, set `_trace_disabled = True` in module state and log `[protocol_traces] AUTO-DISABLED: error rate {pct}% exceeded 20% threshold`. Re-enable on next worker restart.

**Schema validator entry:**
```python
"protocol_trace_observations": [
    "id", "tx_hash", "protocol_slug", "chain", "block_number",
    "from_address", "to_address", "value_eth", "trace_json",
    "call_depth_max", "internal_tx_count", "content_hash", "created_at",
],
```

---

### Pipeline 2: Token Approval Snapshots

**Source:** Blockscout `GET /api/v2/addresses/{address}/token-transfers` (approval events filtered) — OR if the `/token-approvals` endpoint exists on the Blockscout instance, use that directly. **NOTE:** Blockscout's v2 REST API does not have a dedicated `/token-approvals` endpoint on all instances. Fallback: use Etherscan `tokentx` with `topic0=Approval` filter, or parse `eth_getLogs` for Approval events via Alchemy.

**Recommended source:** Alchemy `eth_getLogs` with `Approval(address,address,uint256)` topic for the 6 major stablecoins (USDC, USDT, DAI, FRAX, PYUSD, USDe), filtered to wallet_graph top 500 addresses as `owner`.

**Scope:** 500 wallets × 6 tokens = 3,000 log queries, but batch by token contract with address filter list → **6 calls** with large filter sets (Alchemy supports up to 10K address filters per call)

**Budget impact (Alchemy path):** 6 calls × 75 CU each = **450 CU/day** = 0.045% of 1M daily budget

**Budget impact (Blockscout fallback):** 500 calls = 0.5% of Blockscout daily budget

**Migration:** `091_token_approval_snapshots.sql`
```sql
CREATE TABLE IF NOT EXISTS token_approval_snapshots (
    id BIGSERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    token_address TEXT NOT NULL,
    token_symbol TEXT,
    spender_address TEXT NOT NULL,
    allowance NUMERIC,
    allowance_raw TEXT,
    chain TEXT NOT NULL DEFAULT 'ethereum',
    snapshot_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(wallet_address, token_address, spender_address, chain, snapshot_at)
);

CREATE INDEX IF NOT EXISTS idx_approval_wallet ON token_approval_snapshots(wallet_address, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_spender ON token_approval_snapshots(spender_address, snapshot_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_token ON token_approval_snapshots(token_address, snapshot_at DESC);
```

**Collector:** `app/data_layer/approval_snapshot_collector.py`

**Data flow:**
1. Query `wallet_graph.wallet_risk_scores` for top 500 wallets by `total_stablecoin_value DESC`
2. For each stablecoin contract, fetch `eth_getLogs` with `Approval` topic and wallet addresses as `topics[1]` filter
3. Parse log data → `(owner, spender, amount)`
4. **Diff-capture:** Before INSERT, check most recent row for `(wallet, token, spender)`. Only insert if allowance differs. This prevents unbounded growth — typical churn is <5% of approvals changing per day.
5. content_hash over `(wallet, token, spender, allowance, snapshot_at[:10])`

**Integration:** Enrichment worker, daily gate (`min_hours=24`), group `"data_layer"`, priority 4

**Attestation:** `attest_data_batch("token_approvals", records)`

**Kill-signal:** If Alchemy returns CU quota exceeded (HTTP 429 with `"compute units"` in body), disable for remainder of cycle. If >50% of batches fail, auto-disable until restart.

**Schema validator entry:**
```python
"token_approval_snapshots": [
    "id", "wallet_address", "token_address", "token_symbol",
    "spender_address", "allowance", "allowance_raw", "chain", "snapshot_at",
],
```

---

### Pipeline 3: Oracle Update Cadence Capture

**Source:** Alchemy `eth_call` to Chainlink AggregatorV3 — `latestRoundData()` (already used in oracle_behavior.py) plus `getRoundData(roundId - 1)` to compute inter-update gap

**Scope:** 6 active oracles × 288 samples/day (5-min interval) = **1,728 calls/day**
Each `eth_call` = 26 CU. Two calls per sample (current + previous round).
**Budget impact:** 1,728 × 2 × 26 = **89,856 CU/day** = **9%** of 1M daily budget

**REVISED:** This is higher than estimated in the brief (4.5%). The doubling comes from needing the previous round to compute the gap. Options:
- (A) Accept 9% — still well within budget
- (B) Cache previous round locally and only call `latestRoundData()` → **44,928 CU/day (4.5%)**
- **Recommend (B):** Store last-seen `roundId` and `updatedAt` in-memory; only fetch previous round when `roundId` increments (new on-chain update detected). Between updates, no second call needed. Typical Chainlink feeds update every ~60 min, so the second call fires ~24 times/day per oracle, not 288.

**Revised budget (option B):** 1,728 × 26 (sampling) + 144 × 26 (prev round on update) = **48,672 CU/day = 4.9%**

**Migration:** `092_oracle_update_cadence.sql`
```sql
CREATE TABLE IF NOT EXISTS oracle_update_cadence (
    id BIGSERIAL PRIMARY KEY,
    oracle_address TEXT NOT NULL,
    oracle_name TEXT,
    chain TEXT NOT NULL DEFAULT 'ethereum',
    round_id BIGINT NOT NULL,
    on_chain_updated_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ DEFAULT NOW(),
    answer NUMERIC,
    gap_seconds INTEGER,
    gap_vs_p50 NUMERIC,
    gap_vs_p95 NUMERIC,
    content_hash TEXT,
    UNIQUE(oracle_address, chain, round_id)
);

CREATE INDEX IF NOT EXISTS idx_cadence_oracle ON oracle_update_cadence(oracle_address, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_cadence_gap ON oracle_update_cadence(gap_seconds DESC) WHERE gap_seconds IS NOT NULL;
```

**Collector:** `app/data_layer/oracle_cadence_collector.py`

**Data flow:**
1. Read `oracle_registry WHERE is_active = TRUE` (currently 6 feeds)
2. Every 5 minutes (NOT every cycle — needs its own asyncio task or fast-cycle sub-step), call `latestRoundData()` for each oracle
3. Compare `roundId` to in-memory last-seen. If new round detected:
   - Compute `gap_seconds = new_updatedAt - previous_updatedAt`
   - Fetch rolling p50/p95 from last 100 rows in `oracle_update_cadence` for this oracle
   - Compute `gap_vs_p50` and `gap_vs_p95` (current gap / historical percentile)
   - Store row
4. If `gap_seconds > 2 × p95`, emit a discovery signal (oracle liveness concern)

**Integration:** Two options:
- **(A) Independent asyncio task** in worker main() — fires every 300s regardless of cycle state. Matches the independent diagnostic loop pattern.
- **(B) Fast cycle sub-step** — but fast cycle runs hourly, and we want 5-min resolution. So (A) is required.

**Recommend (A):** Launch `asyncio.create_task(_oracle_cadence_loop())` in `main()` alongside the existing `_diagnostic_loop()`.

**Attestation:** `attest_data_batch("oracle_cadence", records)` — content_hash is SHA-256 of `(oracle_address || round_id || answer || gap_seconds)`

**Kill-signal:** If Alchemy returns 429 or error rate >30% across 3 consecutive 5-min windows, pause oracle cadence loop for 1 hour and log `[oracle_cadence] PAUSED: Alchemy error rate {pct}% over 15 min`. Resume automatically.

**Schema validator entry:**
```python
"oracle_update_cadence": [
    "id", "oracle_address", "oracle_name", "chain", "round_id",
    "on_chain_updated_at", "observed_at", "answer", "gap_seconds",
    "gap_vs_p50", "gap_vs_p95", "content_hash",
],
```

---

### Rate Limiter Update

Add `"alchemy"` to `PROVIDER_CONFIGS` in `app/shared_rate_limiter.py`:
```python
"alchemy": (3.0, 10),  # ~260K calls/day max, well within 1M CU budget
```

Current oracle_behavior.py doesn't go through the rate limiter — it calls Alchemy directly. Pipeline 3 should use `rate_limiter.acquire("alchemy")` before each call.

---

### Deferred (Phase 2)

| Pipeline | Reason | Estimated cost |
|---|---|---|
| Mempool observations | Needs Alchemy Growth ($49/mo) or Blocknative | ~500K CU/day |
| Sub-minute cross-venue spreads | CoinGecko Analyst plan required | N/A (plan upgrade) |
| Protocol composition historical reads | `eth_call` at historical blocks = 26 CU × thousands of blocks | ~2M CU/day |

---

### Summary: Phase 1 Budget Impact

| Pipeline | Provider | Calls/day | Budget % |
|---|---|---|---|
| Protocol traces | Blockscout | 130+13=143 | 0.14% |
| Token approvals | Alchemy | ~150 (batched) | 0.4% CU |
| Oracle cadence | Alchemy | ~1,900 | 4.9% CU |
| **Total new** | | | **Blockscout +0.14%, Alchemy +5.3%** |

No provider crosses 10% of daily budget. CoinGecko and Etherscan budgets unchanged.

---

### File Summary

| Artifact | Path |
|---|---|
| Migration 090 | `migrations/090_protocol_trace_observations.sql` |
| Migration 091 | `migrations/091_token_approval_snapshots.sql` |
| Migration 092 | `migrations/092_oracle_update_cadence.sql` |
| Collector 1 | `app/data_layer/protocol_trace_collector.py` |
| Collector 2 | `app/data_layer/approval_snapshot_collector.py` |
| Collector 3 | `app/data_layer/oracle_cadence_collector.py` |
| Integration 1 | Enrichment worker, daily gate, priority 4 |
| Integration 2 | Enrichment worker, daily gate, priority 4 |
| Integration 3 | Independent asyncio task in main(), 300s interval |
| Rate limiter | Add `"alchemy": (3.0, 10)` to PROVIDER_CONFIGS |
| Schema validator | 3 new entries (38 total) |
