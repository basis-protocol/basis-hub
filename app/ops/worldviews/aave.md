# Aave Governance

## Worldview Summary

Structured proposal lifecycle (ARC -> ARFC -> AIP). Risk providers complement each other (Gauntlet for market risk, Certora for formal verification, Chaos Labs/Sentora for simulation). Community-driven parameter decisions. The governance machine processes proposals through rigorous stages before implementation.

## Key Themes

- **Process legitimacy:** The ARC->ARFC->AIP lifecycle is how ideas become protocol changes. Respect the process.
- **Risk provider ecosystem:** Multiple risk providers, each specialized. They complement, not compete. Gauntlet handles market parameters, Certora does formal verification, Sentora runs simulations.
- **Community governance:** Active delegates (ACI/Marc Zeller, other delegates) drive discussion. Proposals need community support to progress.
- **Stablecoin collateral decisions:** When a new stablecoin is proposed as collateral, the evaluation is ad-hoc. Each listing goes through its own analysis.

## Bridge Patterns

- "Standardized stablecoin input for collateral decisions" — when an ARC proposes adding a new stablecoin, the risk evaluation is one-off. SII provides a standing, versioned quality signal that any proposal can reference.
- "Complement to risk providers" — Gauntlet handles market risk parameters, Sentora handles simulation. Nobody handles ongoing stablecoin quality monitoring as a continuous feed. SII fills that gap.
- "Forum contribution as credibility" — post substantive analysis using SII data on active stablecoin-related proposals. Add value to the discussion. Build reputation through quality contributions.
- "Parameter input, not parameter setting" — SII is an input to decisions, not a decision. The governance process decides. SII provides data.

## Language to Use

- governance input, collateral evaluation, risk complement
- continuous monitoring, versioned methodology, transparent
- community contribution, substantive analysis

## Language to Avoid

- risk rating (implies authority over governance decisions)
- should, must, need to (governance is sovereign)
- better than (don't compare to existing risk providers — complement them)
