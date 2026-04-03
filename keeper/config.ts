export interface KeeperConfig {
  // Chain RPCs
  baseRpcUrl: string;
  arbitrumRpcUrl: string;

  // Contract addresses (per chain)
  baseOracleAddress: string;
  arbitrumOracleAddress: string;

  // Keeper wallet
  privateKey: string;

  // Hub API
  apiBaseUrl: string;               // e.g. "https://basisprotocol.xyz"
  apiSiiScoresEndpoint: string;     // "/api/scores"
  apiPsiScoresEndpoint: string;     // "/api/psi/scores"

  // Thresholds
  siiScoreDeltaThreshold: number;   // Min score change to trigger update (basis points)
  psiScoreDeltaThreshold: number;   // Min PSI score change to trigger update
  maxGasPrice: bigint;              // Max gas price in wei

  // Timing
  cycleIntervalMs: number;          // Time between keeper cycles
  stalenessThreshold: number;       // Max seconds before force-updating
}

export const defaultConfig: Partial<KeeperConfig> = {
  apiSiiScoresEndpoint: "/api/scores",
  apiPsiScoresEndpoint: "/api/psi/scores",
  siiScoreDeltaThreshold: 50,   // 0.5% change
  psiScoreDeltaThreshold: 50,
  cycleIntervalMs: 60_000,      // 1 minute
  stalenessThreshold: 3600,     // 1 hour
};

export function loadConfig(): KeeperConfig {
  const required = [
    "BASE_RPC_URL",
    "ARBITRUM_RPC_URL",
    "BASE_ORACLE_ADDRESS",
    "ARBITRUM_ORACLE_ADDRESS",
    "KEEPER_PRIVATE_KEY",
    "API_BASE_URL",
  ];

  for (const key of required) {
    if (!process.env[key]) {
      throw new Error(`Missing required env var: ${key}`);
    }
  }

  return {
    baseRpcUrl: process.env.BASE_RPC_URL!,
    arbitrumRpcUrl: process.env.ARBITRUM_RPC_URL!,
    baseOracleAddress: process.env.BASE_ORACLE_ADDRESS!,
    arbitrumOracleAddress: process.env.ARBITRUM_ORACLE_ADDRESS!,
    privateKey: process.env.KEEPER_PRIVATE_KEY!,
    apiBaseUrl: process.env.API_BASE_URL!,
    apiSiiScoresEndpoint: process.env.API_SII_ENDPOINT ?? defaultConfig.apiSiiScoresEndpoint!,
    apiPsiScoresEndpoint: process.env.API_PSI_ENDPOINT ?? defaultConfig.apiPsiScoresEndpoint!,
    siiScoreDeltaThreshold: Number(process.env.SII_DELTA_THRESHOLD ?? defaultConfig.siiScoreDeltaThreshold),
    psiScoreDeltaThreshold: Number(process.env.PSI_DELTA_THRESHOLD ?? defaultConfig.psiScoreDeltaThreshold),
    maxGasPrice: BigInt(process.env.MAX_GAS_PRICE ?? "50000000000"), // 50 gwei
    cycleIntervalMs: Number(process.env.CYCLE_INTERVAL_MS ?? defaultConfig.cycleIntervalMs),
    stalenessThreshold: Number(process.env.STALENESS_THRESHOLD ?? defaultConfig.stalenessThreshold),
  };
}
