# Bucket A Go-Live — Pre-flight Report

**Session:** go-live for Bucket A (track-record, disputes, methodology hash)
**Branch:** `claude/track-record-disputes-5RhQP`
**Code commit:** `bef82a0`
**Pre-flight verdict:** **FAIL — DO NOT PROCEED TO STEP 1.**

Per the session's own stop condition ("Report pre-flight results. Do not
proceed to Step 1 if any check fails."), this session halts here. What
follows is the evidence.

---

## Pre-flight check 1 — deployer wallet funding

**Status:** UNVERIFIABLE from this environment.

Evidence: no deployer private key is available in this sandbox. No RPC
endpoint to Base or Arbitrum mainnet is configured. The sandbox cannot
call `cast balance` or equivalent against either chain. This check
cannot be completed without a human operator with wallet access.

---

## Pre-flight check 2 — Oracle upgradeability **(HARD BLOCKER)**

**Status:** FAIL — contract is NOT upgradeable.

Evidence:

- Live oracle address on both chains:
  `0x1651d7b2e238a952167e51a1263ffe607584db83`
  (confirmed in `app/ops/tools/oracle_monitor.py:39`,
  `basis_protocol_integration_guide.md:300-301`,
  `app/ops/routes.py:2610`, `DUNE_QUERIES.md`).
- Original deploy artifact:
  `broadcast/Deploy.s.sol/8453/run-latest.json` — transaction type
  `CREATE`, `contractName: BasisOracle`, deployer
  `0x2df0f62d1861aa59a4430e3b2b2e7a0d29cb723b`, block `0x2a64334`,
  tx `0xa983bd6e0326f91b39fb1f3b12017bc3c7f50e48b711838797274f56afe48ac5`.
  This is a direct `new BasisOracle(keeperAddress)` deployment.
- Source inspection of `src/BasisSIIOracle.sol`:
  - Line 10: `contract BasisOracle is IBasisSIIOracle { ... }` — single
    inheritance, no upgradeable mixin.
  - Line 46: `constructor(address initialKeeper) { ... }` — constructor
    pattern, not `initialize()`.
  - No `_authorizeUpgrade`, no `UUPSUpgradeable`, no `Initializable`,
    no `TransparentUpgradeableProxy`, no Diamond facets anywhere in
    `src/`.
- `lib/openzeppelin-contracts` is vendored but `openzeppelin-contracts-
  upgradeable` is not present.

Consequence: **there is no upgrade path**. Adding `publishTrackRecord`,
`publishDisputeHash`, and `publishMethodologyHash` to the live contract
is impossible without deploying a new contract at a new address.

The session's own Step 1a says:

> For non-upgradeable: this is a blocker — deploying a new Oracle V2
> means an address change, which breaks every consumer. Flag and stop.

**Stopping here.**

### Consumers that would break on an address change

Any of these would need to be migrated before a new oracle address
could go live:

- `keeper/config.ts` — reads `BASE_ORACLE_ADDRESS` and
  `ARBITRUM_ORACLE_ADDRESS` from env. Easy to rotate, but every keeper
  instance must cut over atomically or disputes/track-record writes
  split across two contracts.
- `app/ops/tools/oracle_monitor.py` — hard-codes the address on line
  39. Easy fix.
- `basis_protocol_integration_guide.md` — published integration guide
  at lines 300, 301, 528, 556. External integrators reading this guide
  have the old address pinned.
- `DUNE_QUERIES.md` — public Dune queries filter by the old address.
  External dashboards depending on them break silently.
- Any third-party smart contract that queries the oracle by address
  (e.g. a rating consumer using `IBasisSIIOracle`). Unknown; cannot be
  enumerated from this side.

### Recommended redesign (out of scope for this session — proposing, not executing)

**Option A — "Companion" contract, preserves existing address.**
Deploy a new contract `BasisOracleExtensions` at a new address that
implements only `publishTrackRecord`, `publishDisputeHash`, and
`publishMethodologyHash`. Keeper writes SII scores to the old address
and track-record / dispute / methodology hashes to the new one. No
consumer of the old oracle breaks. Adds one more address to the keeper
config and the integration guide. This is the least-invasive path.

**Option B — Redeploy and migrate.**
Deploy a new `BasisOracle` containing all old + new functions, switch
keeper and all consumers to the new address, deprecate the old one.
Higher risk, requires coordinated rollout, and every external integrator
must update. Not recommended unless the old oracle has other
deficiencies that justify the migration cost.

**Option C — Proxy retrofit.**
Not possible. A constructor-deployed non-upgradeable contract cannot
be retroactively placed behind a proxy at the same address.

The correct choice is **Option A**. It is not this session's place to
make the call; surfacing for the project owner.

---

## Pre-flight check 3 — production API & detectors live

**Status:** UNVERIFIABLE from this environment.

Evidence: no network access has been used to reach
`https://basisprotocol.xyz/api/health` or check whether
`app/track_record.py` detectors are currently executing in the
production worker loop. Even if reachable, the sandbox has no
credentials to query production Postgres to see whether
`collector_cycle_stats` shows track-record detector cycles. Human
operator must confirm.

---

## Pre-flight check 4 — migration 074 conflict

**Status:** PASS (the only check that passes cleanly).

Evidence:

- `migrations/074_track_record_commitments.sql` exists in this branch.
- No migration with number `074` exists on `main` prior to this branch
  (checked `git log origin/main -- 'migrations/074*'` — empty).
- Migrations 075, 076, 077 in this branch are also unique to it.

No conflict. If production's `schema_migrations` tracking table shows
074 as already applied, it must be from this branch being partially
applied out-of-band — that is a separate audit, not a conflict.

---

## Environmental blockers (independent of the 4 checks above)

All of these must be supplied by a human operator; none are
discoverable in this sandbox:

| Requirement | Present? | Evidence |
|---|---|---|
| `forge` binary | NO | `which forge` returned empty |
| `cast` binary | NO | `which cast` returned empty |
| Deployer private key | NO | no `DEPLOYER_PRIVATE_KEY` or `KEEPER_PRIVATE_KEY` in env |
| `BASE_RPC_URL` mainnet | NO | not set |
| `ARBITRUM_RPC_URL` mainnet | NO | not set |
| `DATABASE_URL` production | NO | not set |
| Basescan API key (verification) | NO | not set |
| Arbiscan API key (verification) | NO | not set |
| Network access to basisprotocol.xyz | UNKNOWN | not attempted |

Every step after pre-flight (contract deploy, migration apply, backfill
run, on-chain commit, vector capture) requires at least one of the
above. None can be worked around by more Claude Code autonomy — they
are ownership / credential / tooling gaps that need a human.

---

## Summary

| Step | Blocker |
|---|---|
| Pre-flight check 1 (wallet funding) | no wallet access |
| Pre-flight check 2 (upgradeability) | **contract is non-upgradeable — session's own stop condition** |
| Pre-flight check 3 (detectors live) | no production API access |
| Pre-flight check 4 (migration conflict) | pass |
| Env: forge/cast | not installed |
| Env: credentials | none present |
| Env: RPC/DB URLs | none present |

Stopping at pre-flight. No production or mainnet side-effects executed.
No canonical docs rounded up.

## What the next session needs

Before restarting the go-live attempt, a human operator must:

1. **Decide the redesign** (Option A / B / C above). If A, write the
   `BasisOracleExtensions.sol` contract and its deploy script.
2. **Stand up a deployer environment** with forge, cast, funded
   deployer wallet on both chains, Basescan + Arbiscan verification
   keys, and mainnet RPC URLs.
3. **Grant this sandbox (or a successor) credential access** for the
   production DB and, if automation continues, wallet signing via a
   hardware-backed or KMS-backed signer. Burning a raw private key
   into a sandbox env is not recommended.
4. **Confirm the track-record detectors are running in production**
   and producing detection-cycle rows. If not, fix that first.

Until those are in hand, the ratification gates in
`docs/basis_protocol_v9_3_constitution_amendment.md` cannot close.

## What this session did produce (and not)

- Did NOT deploy any contract to any network (testnet or mainnet).
- Did NOT apply any migration to any database.
- Did NOT call any function on any live contract.
- Did NOT run any backfill.
- Did NOT commit any methodology hash on-chain.
- Did NOT capture any live vectors.
- Did NOT update canonical docs to claim "live" status.
- Did NOT open or merge any PR.
- Did produce this pre-flight report and halt cleanly.
