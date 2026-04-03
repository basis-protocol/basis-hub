/**
 * Differ — compares API scores against on-chain state to determine what needs updating.
 */

import { OnChainSiiScore, OnChainPsiScore } from "./converter";

export interface SiiDelta {
  token: string;
  score: number;      // new score (basis points)
  grade: string;      // bytes2 hex
  timestamp: number;
  version: number;
}

export interface PsiDelta {
  slug: string;
  score: number;
  grade: string;
  timestamp: number;
  version: number;
}

/**
 * Diff SII scores: return entries where the API score differs from on-chain
 * by more than the threshold, or where the on-chain timestamp is stale.
 */
export function diffSiiScores(
  apiScores: OnChainSiiScore[],
  onChainScores: Map<string, { score: number; timestamp: number }>,
  deltaThreshold: number,
  stalenessThreshold: number,
  now: number
): SiiDelta[] {
  const deltas: SiiDelta[] = [];

  for (const api of apiScores) {
    const onChain = onChainScores.get(api.token.toLowerCase());

    if (!onChain) {
      // New token — always publish
      deltas.push({
        token: api.token,
        score: api.score,
        grade: api.grade,
        timestamp: api.timestamp,
        version: api.version,
      });
      continue;
    }

    const scoreDiff = Math.abs(api.score - onChain.score);
    const isStale = (now - onChain.timestamp) > stalenessThreshold;

    if (scoreDiff >= deltaThreshold || isStale) {
      deltas.push({
        token: api.token,
        score: api.score,
        grade: api.grade,
        timestamp: api.timestamp,
        version: api.version,
      });
    }
  }

  return deltas;
}

/**
 * Diff PSI scores: return entries where the API score differs from on-chain
 * by more than the threshold, or where the on-chain timestamp is stale.
 */
export function diffPsiScores(
  apiScores: OnChainPsiScore[],
  onChainScores: Map<string, { score: number; timestamp: number }>,
  deltaThreshold: number,
  stalenessThreshold: number,
  now: number
): PsiDelta[] {
  const deltas: PsiDelta[] = [];

  for (const api of apiScores) {
    const onChain = onChainScores.get(api.slug);

    if (!onChain) {
      deltas.push({
        slug: api.slug,
        score: api.score,
        grade: api.grade,
        timestamp: api.timestamp,
        version: api.version,
      });
      continue;
    }

    const scoreDiff = Math.abs(api.score - onChain.score);
    const isStale = (now - onChain.timestamp) > stalenessThreshold;

    if (scoreDiff >= deltaThreshold || isStale) {
      deltas.push({
        slug: api.slug,
        score: api.score,
        grade: api.grade,
        timestamp: api.timestamp,
        version: api.version,
      });
    }
  }

  return deltas;
}
