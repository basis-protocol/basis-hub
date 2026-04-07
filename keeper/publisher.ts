import { ethers } from "ethers";
import { logger } from "./logger.js";
import { sendAlert } from "./alerter.js";
import type { ScoreUpdate } from "./differ.js";
import type { KeeperConfig } from "./config.js";

const ORACLE_ABI = [
  "function batchUpdateScores(address[] calldata tokens, uint16[] calldata scores, bytes2[] calldata grades, uint48[] calldata timestamps, uint16[] calldata versions) external",
  "function isStale(address token, uint256 maxAge) external view returns (bool)",
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

  const txHash = await withRetry(
    async () => {
      const tx = await (oracle.batchUpdateScores as ethers.ContractMethod)(
        tokens, scores, grades, timestamps, versions,
        {
          nonce,
          gasLimit: BigInt(config.gasLimitPerUpdate),
        }
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
// Helpers
// ============================================================

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
