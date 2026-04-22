import { ethers } from "ethers";
import { logger } from "./logger.js";
import { sendAlert } from "./alerter.js";
import type { ScoreUpdate } from "./differ.js";
import type { KeeperConfig } from "./config.js";

const ORACLE_ABI = [
  "function batchUpdateScores(address[] calldata tokens, uint16[] calldata scores, bytes2[] calldata grades, uint48[] calldata timestamps, uint16[] calldata versions) external",
  "function batchUpdatePsiScores(string[] calldata slugs, uint16[] calldata scores, bytes2[] calldata grades, uint48[] calldata timestamps, uint16[] calldata versions) external",
  "function isStale(address token, uint256 maxAge) external view returns (bool)",
  "function publishReportHash(bytes32 entityId, bytes32 reportHash, bytes4 lensId) external",
  "function publishStateRoot(bytes32 stateRoot) external",
  "function reportTimestamps(bytes32 entityId) external view returns (uint48)",
  "function stateRootTimestamp() external view returns (uint48)",
  // Read-only PSI accessor — used by scripts/diagnose_psi_state.ts to
  // compare per-slug stored state across chains. Returns
  // (score, grade, timestamp, version). Returns all zeros if slug was
  // never published on that chain (mapping default).
  "function getPsiScore(string calldata protocolSlug) external view returns (uint16, bytes2, uint48, uint16)",
  // SII equivalent — read by address, surfaces the same struct shape. The
  // storage name `scores` is auto-generated Solidity public getter.
  "function scores(address token) external view returns (uint16 score, bytes2 grade, uint48 timestamp, uint16 version)",
];

const SBT_ABI = [
  "function mintRating(address recipient, bytes32 entityId, uint8 entityType, uint16 score, bytes2 grade, uint8 confidence, bytes32 reportHash, uint16 methodVersion) external returns (uint256)",
  "function updateRating(uint256 tokenId, uint16 score, bytes2 grade, uint8 confidence, bytes32 reportHash, uint16 methodVersion) external",
  "function entityToToken(bytes32 entityId) external view returns (uint256)",
];

// ============================================================
// Nonce manager — handles concurrent submissions across chains
// ============================================================

class NonceManager {
  private nonces: Map<string, number> = new Map();

  async getCurrentNonce(
    provider: ethers.JsonRpcProvider,
    address: string,
    chainKey: string
  ): Promise<number> {
    const cached = this.nonces.get(chainKey);
    const onChain = await provider.getTransactionCount(address, "pending");
    const nonce = Math.max(cached ?? 0, onChain);
    this.nonces.set(chainKey, nonce + 1);
    return nonce;
  }

  reset(chainKey: string): void {
    this.nonces.delete(chainKey);
  }
}

export const nonceManager = new NonceManager();

// ============================================================
// Retry with exponential backoff + jitter
// ============================================================

export async function withRetry<T>(
  fn: () => Promise<T>,
  config: { maxRetries: number; baseDelay: number; maxDelay: number },
  context: string
): Promise<T> {
  for (let attempt = 0; attempt <= config.maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === config.maxRetries) {
        await sendAlert(`FAILED after ${config.maxRetries} retries: ${context}`, error);
        throw error;
      }
      const delay = Math.min(
        config.baseDelay * Math.pow(2, attempt) + Math.random() * 1000,
        config.maxDelay
      );
      logger.warn(`Retry ${attempt + 1}/${config.maxRetries} in ${Math.round(delay)}ms: ${context}`);
      await sleep(delay);
    }
  }
  throw new Error("unreachable");
}

// ============================================================
// Publisher
// ============================================================

export interface PublishResult {
  chain: string;
  txHash: string;
  updatesCount: number;
  gasUsed?: bigint;
}

export async function publishUpdates(
  updates: ScoreUpdate[],
  provider: ethers.JsonRpcProvider,
  wallet: ethers.Wallet,
  oracleAddress: string,
  chainKey: string,
  config: KeeperConfig
): Promise<PublishResult | null> {
  if (updates.length === 0) {
    logger.info("No updates to publish", { chain: chainKey });
    return null;
  }

  if (config.dryRun) {
    logger.info("DRY RUN — would publish updates", {
      chain: chainKey,
      count: updates.length,
      tokens: updates.map((u) => u.token),
    });
    return null;
  }

  const feeData = await provider.getFeeData();
  const gasPriceGwei = feeData.gasPrice
    ? Number(ethers.formatUnits(feeData.gasPrice, "gwei"))
    : 0;

  if (gasPriceGwei > config.maxGasPriceGwei) {
    const msg = `Gas price ${gasPriceGwei.toFixed(3)} gwei exceeds cap ${config.maxGasPriceGwei} gwei on ${chainKey}`;
    logger.warn(msg);
    await sendAlert(msg);
    return null;
  }

  const oracle = new ethers.Contract(oracleAddress, ORACLE_ABI, wallet);

  const tokens     = updates.map((u) => u.token);
  const scores     = updates.map((u) => u.score);
  const grades     = updates.map((u) => u.grade);
  const timestamps = updates.map((u) => u.timestamp);
  const versions   = updates.map((u) => u.version);

  const nonce = await nonceManager.getCurrentNonce(provider, wallet.address, chainKey);

  let gasLimit: bigint;
  try {
    const gasEstimate = await (oracle.batchUpdateScores as ethers.BaseContractMethod).estimateGas(
      tokens, scores, grades, timestamps, versions
    );
    gasLimit = (gasEstimate * 120n) / 100n;
    logger.info("SII gas estimated", { chain: chainKey, estimate: gasEstimate.toString(), limit: gasLimit.toString() });
  } catch (err) {
    // Enhanced revert diagnostics (diagnose/psi-estimategas-revert). ethers
    // surfaces contract require() messages via `reason` / `shortMessage`;
    // raw revert data is on `data`; the attempted tx params on `transaction`.
    // Also logs batch shape so we can spot array-length mismatches and the
    // first element of each parallel array so the operator can cross-check
    // against on-chain state via scripts/diagnose_psi_state.ts (SII uses
    // the token-address mapping; the PSI script is the closer analog).
    const errAny = err as any;
    logger.warn("SII gas estimate failed — tx would revert, skipping", {
      chain: chainKey,
      method: "batchUpdateScores",
      message: errAny?.message,
      code: errAny?.code,
      reason: errAny?.reason,
      shortMessage: errAny?.shortMessage,
      data: errAny?.data,
      info: errAny?.info,
      txFrom: errAny?.transaction?.from,
      txTo: errAny?.transaction?.to,
      tokensCount: tokens.length,
      scoresCount: scores.length,
      gradesCount: grades.length,
      timestampsCount: timestamps.length,
      versionsCount: versions.length,
      firstToken: tokens[0],
      firstScore: scores[0],
      firstGrade: grades[0],
      firstTimestamp: timestamps[0],
      firstVersion: versions[0],
    });
    return null;
  }

  const txHash = await withRetry(
    async () => {
      const tx = await (oracle.batchUpdateScores as ethers.ContractMethod)(
        tokens, scores, grades, timestamps, versions,
        { nonce, gasLimit }
      );

      logger.info("Transaction submitted", {
        chain: chainKey,
        txHash: tx.hash,
        nonce,
        updatesCount: updates.length,
      });

      const receipt = await tx.wait(1);

      logger.info("Transaction confirmed", {
        chain: chainKey,
        txHash: tx.hash,
        blockNumber: receipt?.blockNumber,
        gasUsed: receipt?.gasUsed?.toString(),
      });

      return tx.hash as string;
    },
    {
      maxRetries: config.maxRetries,
      baseDelay: config.baseRetryDelayMs,
      maxDelay: config.maxRetryDelayMs,
    },
    `batchUpdateScores on ${chainKey}`
  );

  return {
    chain: chainKey,
    txHash,
    updatesCount: updates.length,
  };
}

// ============================================================
// PSI score publishing
// ============================================================

export interface PsiScoreUpdate {
  slug: string;
  score: number;       // uint16 (float * 100)
  grade: string;       // bytes2 hex
  timestamp: number;   // uint48 unix seconds
  version: number;     // uint16
}

export async function publishPsiScores(
  updates: PsiScoreUpdate[],
  provider: ethers.JsonRpcProvider,
  wallet: ethers.Wallet,
  oracleAddress: string,
  chainKey: string,
  config: KeeperConfig
): Promise<PublishResult | null> {
  if (updates.length === 0) {
    logger.info("No PSI updates to publish", { chain: chainKey });
    return null;
  }

  if (config.dryRun) {
    logger.info("DRY RUN — would publish PSI scores", {
      chain: chainKey,
      count: updates.length,
      slugs: updates.map((u) => u.slug),
    });
    return null;
  }

  const feeData = await provider.getFeeData();
  const gasPriceGwei = feeData.gasPrice
    ? Number(ethers.formatUnits(feeData.gasPrice, "gwei"))
    : 0;

  if (gasPriceGwei > config.maxGasPriceGwei) {
    const msg = `Gas price ${gasPriceGwei.toFixed(3)} gwei exceeds cap ${config.maxGasPriceGwei} gwei on ${chainKey}`;
    logger.warn(msg);
    await sendAlert(msg);
    return null;
  }

  const oracle = new ethers.Contract(oracleAddress, ORACLE_ABI, wallet);

  const slugs      = updates.map((u) => u.slug);
  const scores     = updates.map((u) => u.score);
  const grades     = updates.map((u) => u.grade);
  const timestamps = updates.map((u) => u.timestamp);
  const versions   = updates.map((u) => u.version);

  const nonce = await nonceManager.getCurrentNonce(provider, wallet.address, chainKey);

  let psiGasLimit: bigint;
  try {
    const gasEstimate = await (oracle.batchUpdatePsiScores as ethers.BaseContractMethod).estimateGas(
      slugs, scores, grades, timestamps, versions
    );
    psiGasLimit = (gasEstimate * 120n) / 100n;
    logger.info("PSI gas estimated", { chain: chainKey, estimate: gasEstimate.toString(), limit: psiGasLimit.toString() });
  } catch (err) {
    // Enhanced revert diagnostics (diagnose/psi-estimategas-revert). The
    // BasisSIIOracle PSI path has four per-slug requires inside
    // updatePsiScore (called by batchUpdatePsiScores):
    //   - "Basis: empty slug"
    //   - "Basis: score out of range"       (score > 10000)
    //   - "Basis: future timestamp"         (timestamp > block.timestamp)
    //   - "Basis: stale update"             (timestamp <= stored)
    // Any single failing slug reverts the whole batch. This block captures
    // enough context to identify which one fired. Cross-reference with
    // scripts/diagnose_psi_state.ts which reads on-chain state per slug
    // from both Base and Arbitrum.
    const errAny = err as any;
    logger.warn("PSI gas estimate failed — tx would revert, skipping", {
      chain: chainKey,
      method: "batchUpdatePsiScores",
      message: errAny?.message,
      code: errAny?.code,
      reason: errAny?.reason,
      shortMessage: errAny?.shortMessage,
      data: errAny?.data,
      info: errAny?.info,
      txFrom: errAny?.transaction?.from,
      txTo: errAny?.transaction?.to,
      slugsCount: slugs.length,
      scoresCount: scores.length,
      gradesCount: grades.length,
      timestampsCount: timestamps.length,
      versionsCount: versions.length,
      firstSlug: slugs[0],
      firstScore: scores[0],
      firstGrade: grades[0],
      firstTimestamp: timestamps[0],
      firstVersion: versions[0],
    });
    return null;
  }

  const txHash = await withRetry(
    async () => {
      const tx = await (oracle.batchUpdatePsiScores as ethers.ContractMethod)(
        slugs, scores, grades, timestamps, versions,
        { nonce, gasLimit: psiGasLimit }
      );

      logger.info("PSI transaction submitted", {
        chain: chainKey,
        txHash: tx.hash,
        nonce,
        updatesCount: updates.length,
      });

      const receipt = await tx.wait(1);

      logger.info("PSI transaction confirmed", {
        chain: chainKey,
        txHash: tx.hash,
        blockNumber: receipt?.blockNumber,
        gasUsed: receipt?.gasUsed?.toString(),
      });

      return tx.hash as string;
    },
    {
      maxRetries: config.maxRetries,
      baseDelay: config.baseRetryDelayMs,
      maxDelay: config.maxRetryDelayMs,
    },
    `batchUpdatePsiScores on ${chainKey}`
  );

  return {
    chain: chainKey,
    txHash,
    updatesCount: updates.length,
  };
}

// ============================================================
// Report hash publishing
// ============================================================

export interface ReportHashUpdate {
  entityId: string;   // hex bytes32
  reportHash: string; // hex bytes32
  lensId: string;     // hex bytes4
}

export async function publishReportHashes(
  updates: ReportHashUpdate[],
  provider: ethers.JsonRpcProvider,
  wallet: ethers.Wallet,
  oracleAddress: string,
  chainKey: string,
  config: KeeperConfig
): Promise<number> {
  if (updates.length === 0 || config.dryRun) {
    if (config.dryRun && updates.length > 0) {
      logger.info("DRY RUN — would publish report hashes", { chain: chainKey, count: updates.length });
    }
    return 0;
  }

  const oracle = new ethers.Contract(oracleAddress, ORACLE_ABI, wallet);
  let published = 0;

  for (const u of updates) {
    try {
      let reportGasLimit: bigint;
      try {
        const est = await (oracle.publishReportHash as ethers.BaseContractMethod).estimateGas(
          u.entityId, u.reportHash, u.lensId
        );
        reportGasLimit = (est * 120n) / 100n;
      } catch (estErr) {
        // Enhanced revert diagnostics — mirrors the SII/PSI catch blocks
        // so every estimateGas failure surfaces the same structured fields.
        const estErrAny = estErr as any;
        logger.warn("Report hash gas estimate failed — skipping", {
          chain: chainKey,
          method: "publishReportHash",
          entityId: u.entityId.slice(0, 18),
          reportHash: u.reportHash?.slice?.(0, 18),
          lensId: u.lensId,
          message: estErrAny?.message,
          code: estErrAny?.code,
          reason: estErrAny?.reason,
          shortMessage: estErrAny?.shortMessage,
          data: estErrAny?.data,
          info: estErrAny?.info,
          txFrom: estErrAny?.transaction?.from,
          txTo: estErrAny?.transaction?.to,
        });
        continue;
      }

      const nonce = await nonceManager.getCurrentNonce(provider, wallet.address, chainKey);
      const tx = await (oracle.publishReportHash as ethers.ContractMethod)(
        u.entityId, u.reportHash, u.lensId,
        { nonce, gasLimit: reportGasLimit }
      );
      await tx.wait(1);
      published++;
      logger.info("Report hash published", { chain: chainKey, entityId: u.entityId.slice(0, 18), txHash: tx.hash });
    } catch (err) {
      logger.warn("Failed to publish report hash", {
        chain: chainKey,
        entityId: u.entityId.slice(0, 18),
        error: err instanceof Error ? err.message : String(err),
      });
    }
  }

  return published;
}

// ============================================================
// State root publishing
// ============================================================

export async function publishStateRoot(
  stateRootHash: string,
  provider: ethers.JsonRpcProvider,
  wallet: ethers.Wallet,
  oracleAddress: string,
  chainKey: string,
  config: KeeperConfig
): Promise<boolean> {
  if (config.dryRun) {
    logger.info("DRY RUN — would publish state root", { chain: chainKey, hash: stateRootHash.slice(0, 18) });
    return false;
  }

  try {
    const oracle = new ethers.Contract(oracleAddress, ORACLE_ABI, wallet);

    // Check if today's state root is already published
    const existingTs = await oracle.stateRootTimestamp();
    const now = Math.floor(Date.now() / 1000);
    const oneDayAgo = now - 86400;

    if (Number(existingTs) > oneDayAgo) {
      logger.info("State root already published today, skipping", { chain: chainKey });
      return false;
    }

    let stateRootGasLimit: bigint;
    try {
      const est = await (oracle.publishStateRoot as ethers.BaseContractMethod).estimateGas(stateRootHash);
      stateRootGasLimit = (est * 120n) / 100n;
    } catch (estErr) {
      // Enhanced revert diagnostics — consistent shape across every
      // estimateGas catch in this file.
      const estErrAny = estErr as any;
      logger.warn("State root gas estimate failed — tx would revert, skipping", {
        chain: chainKey,
        method: "publishStateRoot",
        stateRootHash: stateRootHash?.slice?.(0, 18),
        message: estErrAny?.message,
        code: estErrAny?.code,
        reason: estErrAny?.reason,
        shortMessage: estErrAny?.shortMessage,
        data: estErrAny?.data,
        info: estErrAny?.info,
        txFrom: estErrAny?.transaction?.from,
        txTo: estErrAny?.transaction?.to,
      });
      return false;
    }

    const nonce = await nonceManager.getCurrentNonce(provider, wallet.address, chainKey);
    const tx = await (oracle.publishStateRoot as ethers.ContractMethod)(
      stateRootHash,
      { nonce, gasLimit: stateRootGasLimit }
    );
    await tx.wait(1);
    logger.info("State root published", { chain: chainKey, hash: stateRootHash.slice(0, 18), txHash: tx.hash });
    return true;
  } catch (err) {
    logger.warn("Failed to publish state root", {
      chain: chainKey,
      error: err instanceof Error ? err.message : String(err),
    });
    return false;
  }
}

// ============================================================
// Helpers
// ============================================================

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
