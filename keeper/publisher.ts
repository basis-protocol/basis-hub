/**
 * Publisher — sends batch update transactions to the on-chain oracle.
 */

import { ethers } from "ethers";
import { SiiDelta, PsiDelta } from "./differ";
import { KeeperConfig } from "./config";

// Minimal ABI for the BasisOracle contract
const ORACLE_ABI = [
  "function batchUpdateScores(address[] tokens, uint16[] scores, bytes2[] grades, uint48[] timestamps, uint16[] versions) external",
  "function batchUpdatePsiScores(string[] slugs, uint16[] scores, bytes2[] grades, uint48[] timestamps, uint16[] versions) external",
  "function getScore(address token) external view returns (uint16 score, bytes2 grade, uint48 timestamp, uint16 version)",
  "function getPsiScore(string slug) external view returns (uint16 score, bytes2 grade, uint48 timestamp, uint16 version)",
  "function getScoredTokenCount() external view returns (uint256)",
  "function getPsiScoreCount() external view returns (uint256)",
  "function getAllScores() external view returns (address[] tokens, tuple(uint16 score, bytes2 grade, uint48 timestamp, uint16 version)[] scores)",
  "function getAllPsiScores() external view returns (string[] slugs, tuple(uint16 score, bytes2 grade, uint48 timestamp, uint16 version)[] scores)",
];

export interface PublishResult {
  chain: string;
  txHash: string;
  updatedCount: number;
  type: "sii" | "psi";
}

function getOracleContract(
  rpcUrl: string,
  oracleAddress: string,
  privateKey: string
): ethers.Contract {
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const wallet = new ethers.Wallet(privateKey, provider);
  return new ethers.Contract(oracleAddress, ORACLE_ABI, wallet);
}

/**
 * Publish SII score deltas to a single chain.
 */
export async function publishSiiUpdates(
  deltas: SiiDelta[],
  rpcUrl: string,
  oracleAddress: string,
  config: KeeperConfig,
  chainName: string
): Promise<PublishResult | null> {
  if (deltas.length === 0) return null;

  const contract = getOracleContract(rpcUrl, oracleAddress, config.privateKey);

  const tokens = deltas.map((d) => d.token);
  const scores = deltas.map((d) => d.score);
  const grades = deltas.map((d) => d.grade);
  const timestamps = deltas.map((d) => d.timestamp);
  const versions = deltas.map((d) => d.version);

  const tx = await contract.batchUpdateScores(tokens, scores, grades, timestamps, versions, {
    maxFeePerGas: config.maxGasPrice,
  });

  const receipt = await tx.wait();

  return {
    chain: chainName,
    txHash: receipt.hash,
    updatedCount: deltas.length,
    type: "sii",
  };
}

/**
 * Publish PSI score deltas to a single chain.
 */
export async function publishPsiUpdates(
  deltas: PsiDelta[],
  rpcUrl: string,
  oracleAddress: string,
  config: KeeperConfig,
  chainName: string
): Promise<PublishResult | null> {
  if (deltas.length === 0) return null;

  const contract = getOracleContract(rpcUrl, oracleAddress, config.privateKey);

  const slugs = deltas.map((d) => d.slug);
  const scores = deltas.map((d) => d.score);
  const grades = deltas.map((d) => d.grade);
  const timestamps = deltas.map((d) => d.timestamp);
  const versions = deltas.map((d) => d.version);

  const tx = await contract.batchUpdatePsiScores(slugs, scores, grades, timestamps, versions, {
    maxFeePerGas: config.maxGasPrice,
  });

  const receipt = await tx.wait();

  return {
    chain: chainName,
    txHash: receipt.hash,
    updatedCount: deltas.length,
    type: "psi",
  };
}

/**
 * Fetch all on-chain SII scores as a Map<lowercaseAddress, {score, timestamp}>.
 */
export async function fetchOnChainSiiScores(
  rpcUrl: string,
  oracleAddress: string
): Promise<Map<string, { score: number; timestamp: number }>> {
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const contract = new ethers.Contract(oracleAddress, ORACLE_ABI, provider);

  const [tokens, scores] = await contract.getAllScores();
  const map = new Map<string, { score: number; timestamp: number }>();

  for (let i = 0; i < tokens.length; i++) {
    map.set(tokens[i].toLowerCase(), {
      score: Number(scores[i].score),
      timestamp: Number(scores[i].timestamp),
    });
  }

  return map;
}

/**
 * Fetch all on-chain PSI scores as a Map<slug, {score, timestamp}>.
 */
export async function fetchOnChainPsiScores(
  rpcUrl: string,
  oracleAddress: string
): Promise<Map<string, { score: number; timestamp: number }>> {
  const provider = new ethers.JsonRpcProvider(rpcUrl);
  const contract = new ethers.Contract(oracleAddress, ORACLE_ABI, provider);

  const [slugs, scores] = await contract.getAllPsiScores();
  const map = new Map<string, { score: number; timestamp: number }>();

  for (let i = 0; i < slugs.length; i++) {
    map.set(slugs[i], {
      score: Number(scores[i].score),
      timestamp: Number(scores[i].timestamp),
    });
  }

  return map;
}
