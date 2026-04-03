/**
 * Keeper — main entry point for the dual-chain SII + PSI score publisher.
 *
 * Each cycle:
 * 1. Fetch SII scores from hub API
 * 2. Fetch PSI scores from hub API
 * 3. Fetch on-chain state from both chains
 * 4. Diff API vs on-chain for both SII and PSI
 * 5. Publish deltas to both chains
 */

import { loadConfig, KeeperConfig } from "./config";
import { convertSiiScore, convertPsiScore, ApiSiiScore, ApiPsiScore } from "./converter";
import { diffSiiScores, diffPsiScores } from "./differ";
import {
  publishSiiUpdates,
  publishPsiUpdates,
  fetchOnChainSiiScores,
  fetchOnChainPsiScores,
  PublishResult,
} from "./publisher";

async function fetchApiSiiScores(config: KeeperConfig): Promise<ApiSiiScore[]> {
  const url = `${config.apiBaseUrl}${config.apiSiiScoresEndpoint}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`SII API error: ${res.status} ${res.statusText}`);
  const data = await res.json();
  return data.scores ?? data;
}

async function fetchApiPsiScores(config: KeeperConfig): Promise<ApiPsiScore[]> {
  const url = `${config.apiBaseUrl}${config.apiPsiScoresEndpoint}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`PSI API error: ${res.status} ${res.statusText}`);
  const data = await res.json();
  return data.scores ?? data;
}

async function runCycle(config: KeeperConfig): Promise<void> {
  const now = Math.floor(Date.now() / 1000);
  console.log(`[keeper] Starting cycle at ${new Date().toISOString()}`);

  // 1. Fetch scores from API (parallel)
  const [apiSii, apiPsi] = await Promise.all([
    fetchApiSiiScores(config),
    fetchApiPsiScores(config),
  ]);

  console.log(`[keeper] Fetched ${apiSii.length} SII scores, ${apiPsi.length} PSI scores from API`);

  // 2. Convert to on-chain format
  const convertedSii = apiSii.map(convertSiiScore);
  const convertedPsi = apiPsi.map(convertPsiScore);

  // 3. Fetch on-chain state from both chains (parallel)
  const chains = [
    { name: "base", rpc: config.baseRpcUrl, oracle: config.baseOracleAddress },
    { name: "arbitrum", rpc: config.arbitrumRpcUrl, oracle: config.arbitrumOracleAddress },
  ];

  for (const chain of chains) {
    console.log(`[keeper] Processing chain: ${chain.name}`);

    const [onChainSii, onChainPsi] = await Promise.all([
      fetchOnChainSiiScores(chain.rpc, chain.oracle),
      fetchOnChainPsiScores(chain.rpc, chain.oracle),
    ]);

    // 4. Diff
    const siiDeltas = diffSiiScores(
      convertedSii, onChainSii,
      config.siiScoreDeltaThreshold, config.stalenessThreshold, now
    );
    const psiDeltas = diffPsiScores(
      convertedPsi, onChainPsi,
      config.psiScoreDeltaThreshold, config.stalenessThreshold, now
    );

    console.log(`[keeper] ${chain.name}: ${siiDeltas.length} SII deltas, ${psiDeltas.length} PSI deltas`);

    // 5. Publish deltas (parallel per type)
    const results: (PublishResult | null)[] = await Promise.all([
      publishSiiUpdates(siiDeltas, chain.rpc, chain.oracle, config, chain.name),
      publishPsiUpdates(psiDeltas, chain.rpc, chain.oracle, config, chain.name),
    ]);

    for (const result of results) {
      if (result) {
        console.log(
          `[keeper] ${result.chain} ${result.type}: published ${result.updatedCount} updates (tx: ${result.txHash})`
        );
      }
    }
  }

  console.log(`[keeper] Cycle complete`);
}

async function main(): Promise<void> {
  const config = loadConfig();
  console.log("[keeper] Starting Basis Protocol keeper");
  console.log(`[keeper] Cycle interval: ${config.cycleIntervalMs}ms`);

  // Run first cycle immediately
  await runCycle(config);

  // Then run on interval
  setInterval(async () => {
    try {
      await runCycle(config);
    } catch (err) {
      console.error("[keeper] Cycle failed:", err);
    }
  }, config.cycleIntervalMs);
}

main().catch((err) => {
  console.error("[keeper] Fatal error:", err);
  process.exit(1);
});
