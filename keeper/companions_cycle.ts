/**
 * Cycle wiring for the three Companion helpers (track-record, dispute,
 * methodology). Owns the per-cycle plumbing — HTTP helpers for the
 * /api/ops admin surface, batch iteration, mark-committed dispatch,
 * per-domain stats — so keeper/index.ts can drop in three one-liner
 * calls (steps 8 / 9 / 10).
 *
 * Authoritative spec: docs/oracle_option_c_keeper_runbook.md §2.3 + §2.4.
 */

import type { ethers } from "ethers";
import { logger } from "./logger.js";
import type { KeeperConfig } from "./config.js";
import {
  publishTrackRecordCompanion,
  publishDisputeCompanion,
  publishMethodologyCompanion,
  type TrackRecordRow,
  type DisputeTransitionRow,
  type MethodologyRow,
} from "./publisher.js";

/** Per-domain per-cycle stats. Surfaced as `keeper_anchors_per_cycle` metric. */
export interface CompanionStepStats {
  domain: "track_record" | "dispute" | "methodology";
  chain: "base" | "arbitrum";
  pending: number;
  success: number;
  dry_run: number;
  skipped: number;   // collision, getReportHash failure, gas estimate failure, etc.
  error: number;    // exception caught by per-entry try/catch
}

const HTTP_TIMEOUT_MS = 15_000;

/**
 * GET request to a hub admin endpoint. Uses x-admin-key header per
 * routes.py:_check_admin_key (bearer is not supported). Returns parsed
 * JSON; throws on non-2xx.
 */
export async function fetchAdminEndpoint(url: string, adminKey: string): Promise<any> {
  const res = await fetch(url, {
    method: "GET",
    headers: { "x-admin-key": adminKey, accept: "application/json" },
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`GET ${url} → HTTP ${res.status}: ${body.slice(0, 200)}`);
  }
  return res.json();
}

/**
 * POST to a /committed/{chain} endpoint with `{tx_hash}` body.
 * Throws on non-2xx.
 */
export async function markCommitted(
  url: string,
  adminKey: string,
  body: { tx_hash: string },
): Promise<void> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "x-admin-key": adminKey,
      "content-type": "application/json",
      accept: "application/json",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(HTTP_TIMEOUT_MS),
  });
  if (!res.ok) {
    const respBody = await res.text().catch(() => "");
    throw new Error(`POST ${url} → HTTP ${res.status}: ${respBody.slice(0, 200)}`);
  }
}

const BATCH_SIZE = 50;

/** Generic step runner. Each domain instantiates with its own typed publishFn. */
export interface CompanionStepArgs<TEntry> {
  stepLabel: string;
  domain: "track_record" | "dispute" | "methodology";
  apiUrl: string;
  adminKey: string;
  chainKey: "base" | "arbitrum";
  oracleAddress: string;
  provider: ethers.JsonRpcProvider;
  wallet: ethers.Wallet;
  config: KeeperConfig;
  pendingUrl: (apiUrl: string, chainKey: string) => string;
  markCommittedUrl: (apiUrl: string, entry: TEntry, chainKey: string) => string;
  entryIdField: (entry: TEntry) => string;  // for logging only
  publishFn: (
    entry: TEntry,
    provider: ethers.JsonRpcProvider,
    wallet: ethers.Wallet,
    oracleAddress: string,
    chainKey: string,
    config: KeeperConfig,
  ) => Promise<string | null>;
  /** Test-only: inject fakes. Production omits. */
  deps?: {
    fetchFn?: typeof fetchAdminEndpoint;
    markCommittedFn?: typeof markCommitted;
  };
}

export async function runCompanionStep<TEntry>(
  args: CompanionStepArgs<TEntry>,
): Promise<CompanionStepStats> {
  const fetchFn = args.deps?.fetchFn ?? fetchAdminEndpoint;
  const markFn = args.deps?.markCommittedFn ?? markCommitted;

  const stats: CompanionStepStats = {
    domain: args.domain,
    chain: args.chainKey,
    pending: 0,
    success: 0,
    dry_run: 0,
    skipped: 0,
    error: 0,
  };

  let pending: TEntry[];
  try {
    const url = args.pendingUrl(args.apiUrl, args.chainKey);
    pending = (await fetchFn(url, args.adminKey)) as TEntry[];
    if (!Array.isArray(pending)) {
      logger.warn(`[${args.stepLabel}] pending response was not an array — treating as empty`, {
        domain: args.domain, chain: args.chainKey,
      });
      pending = [];
    }
  } catch (err) {
    logger.error(`[${args.stepLabel}] ${args.domain} fetch failed`, {
      chain: args.chainKey,
      error: err instanceof Error ? err.message : String(err),
    });
    return stats;
  }

  stats.pending = pending.length;
  logger.info(`[${args.stepLabel}] ${pending.length} ${args.domain} entries pending`, {
    chain: args.chainKey,
  });

  for (const entry of pending.slice(0, BATCH_SIZE)) {
    const entryId = args.entryIdField(entry);
    try {
      const txHash = await args.publishFn(
        entry, args.provider, args.wallet, args.oracleAddress, args.chainKey, args.config,
      );

      if (args.config.dryRun) {
        stats.dry_run++;
        continue;
      }

      if (txHash) {
        try {
          await markFn(
            args.markCommittedUrl(args.apiUrl, entry, args.chainKey),
            args.adminKey,
            { tx_hash: txHash },
          );
          stats.success++;
        } catch (markErr) {
          // Tx landed on chain (or was already there) but hub couldn't be
          // updated. Log loudly — next cycle will retry the publish, hit
          // the idempotent path, and try mark-committed again.
          logger.error(`[${args.stepLabel}] mark-committed failed (tx already on chain)`, {
            chain: args.chainKey, entryId, txHash,
            error: markErr instanceof Error ? markErr.message : String(markErr),
          });
          stats.error++;
        }
      } else {
        // Companion returned null without dryRun → collision or transient
        // failure. Companion already logged the specific reason at warn.
        stats.skipped++;
      }
    } catch (err) {
      logger.error(`[${args.stepLabel}] entry exception`, {
        chain: args.chainKey, entryId,
        error: err instanceof Error ? err.message : String(err),
      });
      stats.error++;
    }
  }

  logger.info(`[${args.stepLabel}] ${args.domain} stats`, { ...stats });
  return stats;
}

// ===========================================================================
// Domain-specific wrappers — concrete URL builders + Companion dispatch.
// ===========================================================================

export function trackRecordStepArgs(opts: {
  apiUrl: string;
  adminKey: string;
  chainKey: "base" | "arbitrum";
  oracleAddress: string;
  provider: ethers.JsonRpcProvider;
  wallet: ethers.Wallet;
  config: KeeperConfig;
  deps?: CompanionStepArgs<TrackRecordRow>["deps"];
}): CompanionStepArgs<TrackRecordRow> {
  return {
    stepLabel: "step 8",
    domain: "track_record",
    ...opts,
    pendingUrl: (apiUrl, chainKey) =>
      `${apiUrl}/api/ops/track-record/pending-on-chain?chain=${chainKey}`,
    markCommittedUrl: (apiUrl, entry, chainKey) =>
      `${apiUrl}/api/ops/track-record/entries/${entry.entry_id}/committed/${chainKey}`,
    entryIdField: (e) => e.entry_id,
    publishFn: publishTrackRecordCompanion,
  };
}

export function disputeStepArgs(opts: {
  apiUrl: string;
  adminKey: string;
  chainKey: "base" | "arbitrum";
  oracleAddress: string;
  provider: ethers.JsonRpcProvider;
  wallet: ethers.Wallet;
  config: KeeperConfig;
  deps?: CompanionStepArgs<DisputeTransitionRow>["deps"];
}): CompanionStepArgs<DisputeTransitionRow> {
  return {
    stepLabel: "step 9",
    domain: "dispute",
    ...opts,
    pendingUrl: (apiUrl, chainKey) =>
      `${apiUrl}/api/ops/disputes/pending-on-chain?chain=${chainKey}`,
    markCommittedUrl: (apiUrl, entry, chainKey) =>
      `${apiUrl}/api/ops/disputes/transitions/${entry.transition_id}/committed/${chainKey}`,
    entryIdField: (e) => e.transition_id,
    publishFn: publishDisputeCompanion,
  };
}

export function methodologyStepArgs(opts: {
  apiUrl: string;
  adminKey: string;
  chainKey: "base" | "arbitrum";
  oracleAddress: string;
  provider: ethers.JsonRpcProvider;
  wallet: ethers.Wallet;
  config: KeeperConfig;
  deps?: CompanionStepArgs<MethodologyRow>["deps"];
}): CompanionStepArgs<MethodologyRow> {
  return {
    stepLabel: "step 10",
    domain: "methodology",
    ...opts,
    pendingUrl: (apiUrl, chainKey) =>
      `${apiUrl}/api/ops/methodology/pending-on-chain?chain=${chainKey}`,
    markCommittedUrl: (apiUrl, entry, chainKey) =>
      `${apiUrl}/api/ops/methodology/${entry.methodology_id}/committed/${chainKey}`,
    entryIdField: (e) => e.methodology_id,
    publishFn: publishMethodologyCompanion,
  };
}
