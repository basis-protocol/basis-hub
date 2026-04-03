/**
 * Converter — maps API responses to on-chain data types.
 *
 * SII scores are keyed by token address. PSI scores are keyed by protocol slug string.
 * Grades are converted from string ("A+", "B") to bytes2 for on-chain storage.
 */

// ─── Types ───

export interface ApiSiiScore {
  token_address: string;  // 0x... checksummed
  score: number;          // 0-100 (float)
  grade: string;          // "A+", "B", "C-", etc.
  timestamp: number;      // Unix epoch seconds
  version: number;        // Formula version
}

export interface ApiPsiScore {
  protocol_slug: string;  // "aave", "drift", "compound", etc.
  score: number;          // 0-100 (float)
  grade: string;          // "A+", "B", etc.
  timestamp: number;      // Unix epoch seconds
  version: number;        // Formula version
}

export interface OnChainSiiScore {
  token: string;          // address
  score: number;          // 0-10000 (basis points)
  grade: string;          // hex bytes2
  timestamp: number;
  version: number;
}

export interface OnChainPsiScore {
  slug: string;
  score: number;          // 0-10000
  grade: string;          // hex bytes2
  timestamp: number;
  version: number;
}

// ─── Converters ───

/** Convert a human-readable grade to a 2-byte hex string for on-chain storage. */
export function gradeToBytes2(grade: string): string {
  // Pad to 2 chars: "A+" stays "A+", "B" becomes "B "
  const padded = grade.padEnd(2, " ");
  const byte1 = padded.charCodeAt(0);
  const byte2 = padded.charCodeAt(1);
  return "0x" + byte1.toString(16).padStart(2, "0") + byte2.toString(16).padStart(2, "0");
}

/** Convert a score from 0-100 float to 0-10000 basis points. */
export function scoreToBasisPoints(score: number): number {
  return Math.round(score * 100);
}

/** Convert API SII score to on-chain format. */
export function convertSiiScore(api: ApiSiiScore): OnChainSiiScore {
  return {
    token: api.token_address,
    score: scoreToBasisPoints(api.score),
    grade: gradeToBytes2(api.grade),
    timestamp: api.timestamp,
    version: api.version,
  };
}

/** Convert API PSI score to on-chain format. */
export function convertPsiScore(api: ApiPsiScore): OnChainPsiScore {
  return {
    slug: api.protocol_slug,
    score: scoreToBasisPoints(api.score),
    grade: gradeToBytes2(api.grade),
    timestamp: api.timestamp,
    version: api.version,
  };
}
