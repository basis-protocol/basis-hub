/**
 * Oracle entityId computation — canonical TypeScript implementation.
 * ===================================================================
 * Single source of truth for the bytes32 entityId that the keeper
 * publishes to BasisSIIOracle.publishReportHash on Base + Arbitrum.
 *
 * The byte spec is defined in docs/oracle_option_c_routing.md §11 Q2
 * (amended 2026-05-03). This module mirrors the Python reference
 * implementation in app/oracle_keys.py byte-for-byte. Both must
 * reproduce the 15 worked-example hexes in the spec doc and in
 * docs/oracle_option_c_golden_vectors.json — CI fails if either
 * implementation diverges.
 *
 * Do NOT inline this logic at call sites. The publisher's three
 * Companion helpers (PR-3+) delegate here.
 */

import { ethers } from "ethers";

// Domain prefixes — UTF-8 literal bytes, exact match required.
// Any change to these strings is a v2 domain prefix and a new
// entityId space. Never edit in place. See spec §11 Q2 encoding rules.
export const DOMAIN_TRACK_RECORD: Uint8Array = ethers.toUtf8Bytes("basis:track_record:v1");
export const DOMAIN_DISPUTE:      Uint8Array = ethers.toUtf8Bytes("basis:dispute:v1");
export const DOMAIN_METHODOLOGY:  Uint8Array = ethers.toUtf8Bytes("basis:methodology:v1");

/**
 * bytes4(keccak256(utf8(fieldValue))) — Solidity function-selector idiom.
 * Used for both trigger_kind (track-record) and transition_kind (dispute).
 */
function selector4(fieldValue: string): Uint8Array {
  const full = ethers.getBytes(ethers.keccak256(ethers.toUtf8Bytes(fieldValue)));
  return full.slice(0, 4);
}

/**
 * 8-byte big-endian uint64 encoding.
 * Accepts number or bigint; throws if value doesn't fit in uint64.
 */
function uint64BE(n: number | bigint): Uint8Array {
  const big = typeof n === "bigint" ? n : BigInt(Math.floor(n));
  if (big < 0n || big > 0xFFFFFFFFFFFFFFFFn) {
    throw new RangeError(`uint64BE: value ${big} does not fit in uint64`);
  }
  const buf = new Uint8Array(8);
  new DataView(buf.buffer).setBigUint64(0, big, false); // false = big-endian
  return buf;
}

/**
 * Coerce a Date / ISO-8601 string / unix-seconds number to int seconds.
 *
 * Sub-second precision is dropped; collisions at 1-second granularity
 * are by definition the same event (per spec §11 Q2 encoding rules).
 */
function toUnixSeconds(value: number | Date | string): number {
  if (typeof value === "number") return Math.floor(value);
  if (value instanceof Date) return Math.floor(value.getTime() / 1000);
  // ISO-8601 string — Date constructor handles "...Z" natively.
  const ms = new Date(value).getTime();
  if (Number.isNaN(ms)) {
    throw new Error(`toUnixSeconds: cannot parse ${JSON.stringify(value)} as ISO-8601 date`);
  }
  return Math.floor(ms / 1000);
}

/**
 * Concatenate Uint8Arrays into a single buffer.
 * (ethers.concat exists but accepts BytesLike; this avoids the type
 * juggling and keeps the call site obvious.)
 */
function concatBytes(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let off = 0;
  for (const p of parts) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

/**
 * entityId for a track-record event row.
 *
 * Preimage per spec §11 Q2:
 *   DOMAIN_TRACK_RECORD || bytes4(keccak(trigger_kind))
 *                       || utf8(entity_slug)
 *                       || uint64_be(triggered_at_unix)
 */
export function trackRecordEntityId(
  entitySlug: string,
  triggerKind: string,
  triggeredAt: number | Date | string,
): string {
  const preimage = concatBytes([
    DOMAIN_TRACK_RECORD,
    selector4(triggerKind),
    ethers.toUtf8Bytes(entitySlug),
    uint64BE(toUnixSeconds(triggeredAt)),
  ]);
  return ethers.keccak256(preimage);
}

/**
 * entityId for a dispute_transitions row.
 *
 * Preimage per spec §11 Q2 (amended to include transition_index so
 * the entityId matches the schema's UNIQUE(dispute_id, transition_index)
 * natural key):
 *   DOMAIN_DISPUTE || keccak(utf8(`dispute:${dispute_id}`))
 *                  || bytes4(keccak(transition_kind))
 *                  || uint64_be(transition_index)
 */
export function disputeEntityId(
  disputeId: string,
  transitionKind: string,
  transitionIndex: number,
): string {
  const disputeIdBytes32 = ethers.getBytes(
    ethers.keccak256(ethers.toUtf8Bytes(`dispute:${disputeId}`)),
  );
  const preimage = concatBytes([
    DOMAIN_DISPUTE,
    disputeIdBytes32,
    selector4(transitionKind),
    uint64BE(transitionIndex),
  ]);
  return ethers.keccak256(preimage);
}

/**
 * entityId for a methodology_hashes row.
 *
 * Preimage per spec §11 Q2:
 *   DOMAIN_METHODOLOGY || utf8(methodology_id)
 *
 * methodology_id is taken raw — no normalization, no whitespace trim,
 * no case folding. The methodology_hashes.methodology_id column is
 * canonical.
 */
export function methodologyEntityId(methodologyId: string): string {
  const preimage = concatBytes([
    DOMAIN_METHODOLOGY,
    ethers.toUtf8Bytes(methodologyId),
  ]);
  return ethers.keccak256(preimage);
}

// Internal helpers exported for tests only.
export const __test__ = { selector4, uint64BE, toUnixSeconds };
