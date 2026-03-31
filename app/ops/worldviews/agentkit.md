# AgentKit / Coinbase

## Worldview Summary

Agents need financial autonomy. MCP as tool integration standard. x402 for stablecoin payments. The Base ecosystem as the agent-native L2. AgentKit provides the execution layer for AI agents in DeFi — but agents can execute without perceiving risk.

## Key Themes

- **Agent financial autonomy:** Agents should be able to hold, send, and manage funds. AgentKit + MPC wallets make this possible.
- **MCP as standard:** Model Context Protocol is the integration standard for agent tools. Any capability exposed via MCP is immediately available to every agent framework.
- **x402 = stablecoin payments:** HTTP 402 Payment Required, implemented with stablecoin micropayments. Agents pay for services with stablecoins.
- **Base = agent L2:** Coinbase's L2 is positioning as the agent-native chain. Low fees, fast finality, Coinbase custody integration.
- **Execution without perception:** AgentKit enables agents to swap, lend, bridge — but they can't assess whether the stablecoin they're about to accept is deteriorating.

## Bridge Patterns

- "Perception layer for agent finance" — agents can execute but can't perceive quality. SII via MCP gives agents a stablecoin quality signal before they transact.
- "x402 needs quality" — if agents pay with stablecoins, which stablecoin? Quality scoring helps agents select the right stablecoin for payments.
- "MCP integration" — Basis already has an MCP server. AgentKit examples that use Basis MCP tools demonstrate the integration pattern.
- "Developer discovery" — publish integration examples. Developers building on AgentKit find Basis MCP tools through documentation, npm, GitHub examples.

## Language to Use

- agent perception, quality signal, MCP tool
- stablecoin selection, risk-aware agents, pre-transaction check
- integration, developer experience, example

## Language to Avoid

- gatekeeper (agents should be autonomous)
- blocking, preventing (SII informs, doesn't block)
- centralized (antithetical to agent autonomy thesis)
