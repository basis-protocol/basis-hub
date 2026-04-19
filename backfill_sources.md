# Backfill Sources

Every row documents the primary and fallback data source for each index component.
Where Blockscout is not primary, a rationale is provided.

| Index | Component Category | Primary Source | Fallback | Solana Source | Rationale (if not Blockscout primary) |
|-------|-------------------|----------------|----------|---------------|---------------------------------------|
| PSI | Smart contract | Blockscout V2 | — | Helius | — |
| PSI | TVL / liquidity | DeFiLlama API | — | DeFiLlama | DeFiLlama is the only aggregated cross-protocol TVL history source; Blockscout per-pool reads would require replicating DeFiLlama's adapter set |
| PSI | Governance (on-chain) | Blockscout logs | Tally API | Helius | — |
| PSI | Governance (off-chain) | Snapshot API | — | Snapshot | Off-chain votes not on any blockchain |
| PSI | Revenue / fees | DeFiLlama | — | DeFiLlama | Fee aggregation requires protocol-specific revenue accounting; DeFiLlama already normalizes this |
| RPI | Parameter changes | Blockscout logs | Etherscan V2 fallback | Helius | — |
| RPI | Governance proposals | Snapshot / Tally | — | Snapshot | Off-chain governance not on-chain |
| RPI | Protocol docs scoring | Firecrawl (existing) | — | Same | Document scoring requires rendered HTML, not on-chain data |
| RPI | Incident history | Rekt / manual | — | Same | Exploit databases are off-chain editorial sources |
| LSTI | Peg / price | CoinGecko | — | CoinGecko | Price feeds are off-chain market data; no on-chain equivalent for historical CEX prices |
| LSTI | Supply history | Blockscout | — | Helius | — |
| LSTI | TVL | DeFiLlama | — | DeFiLlama | Same as PSI TVL rationale |
| BRI | Bridge volume | BLOCKED (DeFiLlama Pro, V9.3) | Blockscout transfers on bridge contracts | N/A | DeFiLlama paywalled bridges endpoint; direct contract monitoring deferred to Phase 2 |
| BRI | Uptime | Existing monitors | — | N/A | Uptime is derived from our own monitoring, not on-chain |
| DOHI | Proposals | Snapshot | Tally | Snapshot | Off-chain governance |
| VSRI | Yield / TVL | DeFiLlama | — | DeFiLlama | Same as PSI TVL rationale |
| CXRI | Reserves | Issuer PDFs (CDA) | — | Same | Exchange reserves published off-chain as attestation reports |
| TTI | NAV | Issuer reports | Blockscout mint events | N/A | NAV is issuer-reported; mint events can corroborate supply but not composition |
