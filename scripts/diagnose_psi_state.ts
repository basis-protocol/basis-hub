/**
 * PSI on-chain state diagnostic.
 *
 * Read-only cross-chain check: for every PSI slug the hub is currently
 * publishing, print the stored state on both Base and Arbitrum side-by-side
 * and flag drift. Built in response to the observed keeper behavior where
 * `batchUpdatePsiScores` succeeds on one chain and reverts with
 * `estimateGas failed` on the other from the same wallet, same cycle
 * (SII publishes successfully on both chains in the same cycle, so it
 * isn't an auth or basic-connectivity issue).
 *
 * The BasisSIIOracle PSI path has four per-slug requires inside
 * `updatePsiScore` (called by `batchUpdatePsiScores`):
 *
 *   1. `bytes(protocolSlug).length > 0`          → "Basis: empty slug"
 *   2. `score <= 10000`                          → "Basis: score out of range"
 *   3. `timestamp <= uint48(block.timestamp)`    → "Basis: future timestamp"
 *   4. `timestamp > psiScores[slugHash].timestamp` → "Basis: stale update"
 *
 * Any ONE failing slug reverts the entire batch. The most likely cause of
 * one-chain-only revert is (4): a prior cycle published a PSI batch on one
 * chain and failed on the other, leaving the stored timestamp on the
 * "ahead" chain >= the current cycle's timestamp → keeper submits a batch
 * where at least one slug's timestamp is not strictly greater than the
 * stored value → revert. This diagnostic surfaces exactly that.
 *
 * Usage:
 *   # Read-only; no private key required.
 *   BASIS_API_URL=https://basisprotocol.xyz \
 *   BASE_RPC_URL=https://base-mainnet.g.alchemy.com/v2/... \
 *   ARBITRUM_RPC_URL=https://arb-mainnet.g.alchemy.com/v2/... \
 *   BASE_ORACLE_ADDRESS=0x1651d7b2E238a952167E51A1263FFe607584DB83 \
 *   ARBITRUM_ORACLE_ADDRESS=0x1651d7b2E238a952167E51A1263FFe607584DB83 \
 *   npx tsx scripts/diagnose_psi_state.ts
 *
 * Output: one line per slug with (Base score/ts/version | Arbitrum score/ts/version
 * | drift flags). Summary at the end lists slugs that would block
 * `batchUpdatePsiScores` on each chain for the current cycle timestamp.
 *
 * IMPORTANT: This script is read-only. It does not submit transactions,
 * require a private key, or modify any state. Safe to run from any
 * environment that can reach the hub API and both RPC endpoints.
 */

import { ethers } from "ethers";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const ORACLE_READ_ABI = [
  "function getPsiScore(string calldata protocolSlug) external view returns (uint16 score, bytes2 grade, uint48 timestamp, uint16 version)",
  "function getPsiScoreCount() external view returns (uint256)",
];

interface ChainContext {
  key: "base" | "arbitrum";
  rpcUrl: string;
  oracleAddress: string;
  chainId: number;
}

interface HubPsiRow {
  protocol_slug: string;
  score: number;      // 0-100 from the hub API
  grade: string;
  computed_at?: string;
}

interface HubPsiResponse {
  protocols: HubPsiRow[];
}

interface OnChainRow {
  score: number;      // 0-10000 (hub*100)
  grade: string;      // bytes2 hex
  timestamp: number;  // unix seconds
  version: number;
  exists: boolean;    // false when all fields are zero (mapping default)
}

function requireEnv(key: string): string {
  const v = process.env[key];
  if (!v) {
    throw new Error(`Missing required env var: ${key}`);
  }
  return v;
}

function buildContexts(): ChainContext[] {
  return [
    {
      key: "base",
      rpcUrl: requireEnv("BASE_RPC_URL"),
      oracleAddress: requireEnv("BASE_ORACLE_ADDRESS"),
      chainId: 8453,
    },
    {
      key: "arbitrum",
      rpcUrl: requireEnv("ARBITRUM_RPC_URL"),
      oracleAddress: requireEnv("ARBITRUM_ORACLE_ADDRESS"),
      chainId: 42161,
    },
  ];
}

// ---------------------------------------------------------------------------
// Fetch hub state
// ---------------------------------------------------------------------------

async function fetchHubPsiScores(apiUrl: string): Promise<HubPsiRow[]> {
  const url = `${apiUrl}/api/psi/scores`;
  const res = await fetch(url, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(30_000),
  });
  if (!res.ok) {
    throw new Error(`PSI API returned HTTP ${res.status}: ${await res.text()}`);
  }
  const raw = (await res.json()) as HubPsiResponse;
  return (raw.protocols || []).filter((p) => p.score != null && p.grade);
}

// ---------------------------------------------------------------------------
// Read on-chain PSI state
// ---------------------------------------------------------------------------

async function readOnChainPsi(
  ctx: ChainContext,
  slug: string
): Promise<OnChainRow> {
  const provider = new ethers.JsonRpcProvider(ctx.rpcUrl);
  const oracle = new ethers.Contract(ctx.oracleAddress, ORACLE_READ_ABI, provider);

  // getPsiScore returns (score, grade, timestamp, version). On slugs that
  // were never published, all fields default to 0 / 0x0000.
  const [rawScore, rawGrade, rawTs, rawVer] = await oracle.getPsiScore(slug) as [
    bigint, string, bigint, bigint,
  ];
  const score = Number(rawScore);
  const grade = (rawGrade || "").toLowerCase();
  const timestamp = Number(rawTs);
  const version = Number(rawVer);
  const exists = score !== 0 || timestamp !== 0 || version !== 0
    || (grade !== "0x0000" && grade !== "");

  return { score, grade, timestamp, version, exists };
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function pad(s: string, n: number): string {
  return s.length >= n ? s : s + " ".repeat(n - s.length);
}

function fmtTs(unix: number): string {
  if (!unix) return "(unset)";
  return new Date(unix * 1000).toISOString().replace("T", " ").replace(".000Z", "Z");
}

async function main(): Promise<void> {
  const apiUrl = process.env.BASIS_API_URL || "https://basisprotocol.xyz";
  const chains = buildContexts();

  console.log(`[diagnose_psi_state] api=${apiUrl}`);
  console.log(
    `[diagnose_psi_state] chains=${chains.map((c) => `${c.key}(${c.chainId})`).join(", ")}\n`
  );

  const hubRows = await fetchHubPsiScores(apiUrl);
  console.log(`[diagnose_psi_state] hub returned ${hubRows.length} scored protocols`);

  // Current cycle's would-submit timestamp — what the keeper would send this
  // instant. The PSI check that most often fires one-chain-only is
  // `timestamp > stored` (= "Basis: stale update").
  const cycleTs = Math.floor(Date.now() / 1000);
  console.log(`[diagnose_psi_state] cycle_ts=${cycleTs} (${fmtTs(cycleTs)})\n`);

  const header = [
    pad("slug", 28),
    pad("hub_score", 10),
    pad("hub_grade", 10),
    pad("base(score/ts/ver)", 36),
    pad("arb(score/ts/ver)", 36),
    "drift",
  ].join(" ");
  console.log(header);
  console.log("-".repeat(header.length));

  const baseStaleSlugs: string[] = [];
  const arbStaleSlugs: string[] = [];
  const baseMissingSlugs: string[] = [];
  const arbMissingSlugs: string[] = [];
  const versionDriftSlugs: Array<{ slug: string; base: number; arb: number }> = [];
  let baseReadErrors = 0;
  let arbReadErrors = 0;

  for (const row of hubRows) {
    const slug = row.protocol_slug;
    const hubScoreScaled = Math.round(row.score * 100);

    let base: OnChainRow | null = null;
    let arb: OnChainRow | null = null;
    try {
      base = await readOnChainPsi(chains[0], slug);
    } catch (e) {
      baseReadErrors++;
      console.error(`[read-error base] ${slug}: ${(e as Error).message}`);
    }
    try {
      arb = await readOnChainPsi(chains[1], slug);
    } catch (e) {
      arbReadErrors++;
      console.error(`[read-error arb] ${slug}: ${(e as Error).message}`);
    }

    const driftFlags: string[] = [];

    if (base && !base.exists) baseMissingSlugs.push(slug);
    if (arb && !arb.exists) arbMissingSlugs.push(slug);

    // The "stale update" require: `timestamp > stored`. If stored >= cycleTs
    // for any slug in the batch, the whole batchUpdatePsiScores reverts.
    if (base && base.exists && base.timestamp >= cycleTs) baseStaleSlugs.push(slug);
    if (arb && arb.exists && arb.timestamp >= cycleTs) arbStaleSlugs.push(slug);

    // Cross-chain version drift: stored version on one chain strictly greater
    // than the other. Informational — the contract does not enforce a
    // monotonic version invariant on the PSI path (only on SII reports),
    // but version drift often travels with timestamp drift.
    if (base && arb && base.exists && arb.exists && base.version !== arb.version) {
      versionDriftSlugs.push({ slug, base: base.version, arb: arb.version });
      driftFlags.push(`version_mismatch(b=${base.version},a=${arb.version})`);
    }

    // Score-range precheck for require (2): score <= 10000 when submitting.
    if (hubScoreScaled > 10000) {
      driftFlags.push(`hub_score_overflow(${hubScoreScaled})`);
    }

    // Flag slugs that would block the current cycle's batchUpdatePsiScores.
    if (base && base.exists && base.timestamp >= cycleTs) {
      driftFlags.push(`base_would_revert_stale(stored_ts=${base.timestamp})`);
    }
    if (arb && arb.exists && arb.timestamp >= cycleTs) {
      driftFlags.push(`arb_would_revert_stale(stored_ts=${arb.timestamp})`);
    }

    const baseStr = base
      ? (base.exists
          ? `${base.score}/${fmtTs(base.timestamp)}/${base.version}`
          : "(unset)")
      : "(read error)";
    const arbStr = arb
      ? (arb.exists
          ? `${arb.score}/${fmtTs(arb.timestamp)}/${arb.version}`
          : "(unset)")
      : "(read error)";

    console.log([
      pad(slug, 28),
      pad(String(hubScoreScaled), 10),
      pad(row.grade, 10),
      pad(baseStr, 36),
      pad(arbStr, 36),
      driftFlags.length ? driftFlags.join(",") : "-",
    ].join(" "));
  }

  console.log("");
  console.log("================ SUMMARY ================");
  console.log(`hub_protocols=${hubRows.length}`);
  console.log(`base read errors=${baseReadErrors}`);
  console.log(`arb  read errors=${arbReadErrors}`);
  console.log(`slugs missing on base: ${baseMissingSlugs.length}`);
  if (baseMissingSlugs.length) {
    console.log(`  ${baseMissingSlugs.join(", ")}`);
  }
  console.log(`slugs missing on arb:  ${arbMissingSlugs.length}`);
  if (arbMissingSlugs.length) {
    console.log(`  ${arbMissingSlugs.join(", ")}`);
  }
  console.log(`version drift (base != arb): ${versionDriftSlugs.length}`);
  for (const v of versionDriftSlugs) {
    console.log(`  ${v.slug}: base=${v.base} arb=${v.arb}`);
  }
  console.log("");
  console.log(
    `slugs that would block batchUpdatePsiScores on BASE this cycle ` +
    `(timestamp >= ${cycleTs}): ${baseStaleSlugs.length}`
  );
  if (baseStaleSlugs.length) {
    console.log(`  ${baseStaleSlugs.join(", ")}`);
  }
  console.log(
    `slugs that would block batchUpdatePsiScores on ARBITRUM this cycle ` +
    `(timestamp >= ${cycleTs}): ${arbStaleSlugs.length}`
  );
  if (arbStaleSlugs.length) {
    console.log(`  ${arbStaleSlugs.join(", ")}`);
  }
  console.log("=========================================");

  // Exit code reflects the most likely reverts: nonzero if at least one
  // chain has a stale-update conflict for the current cycle.
  if (baseStaleSlugs.length > 0 || arbStaleSlugs.length > 0) {
    console.log("");
    console.log(
      "DIAGNOSIS: at least one chain has at least one slug with " +
      "stored timestamp >= the current cycle timestamp. The require() that " +
      "will fire is updatePsiScore's `timestamp > psiScores[slugHash].timestamp` " +
      `("Basis: stale update"). ` +
      "Fix candidates (to be addressed in a separate PR):\n" +
      "  - ensure per-chain cycle timestamps advance independently, OR\n" +
      "  - skip already-up-to-date slugs per chain in the keeper's differ, OR\n" +
      "  - bump cycleTimestamp to NOW() on every cycle and tolerate occasional drift"
    );
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("diagnose_psi_state failed:", err);
  process.exit(2);
});
