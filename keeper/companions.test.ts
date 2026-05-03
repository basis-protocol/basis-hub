/**
 * Tests for the three Companion helpers in keeper/publisher.ts.
 *
 * Approach: build a fake oracle satisfying CompanionOracleLike with
 * canned getReportHash + publishReportHash behaviors, then drive
 * runCompanion through every branch:
 *   - first-write (existing hash = ZeroHash)
 *   - idempotent no-op (existing hash = same as new)
 *   - collision refusal (existing hash = different from new)
 *   - DRY_RUN (config.dryRun = true)
 *   - getReportHash failure
 *   - estimateGas failure
 *   - tx send failure
 *
 * Plus end-to-end coverage of the three exported wrappers
 * (publishTrackRecordCompanion / publishDisputeCompanion /
 *  publishMethodologyCompanion) confirming entityId / lens dispatch.
 *
 * Run: `npx tsx --test keeper/companions.test.ts`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ethers } from "ethers";

import {
  LENS_TRACK_RECORD,
  LENS_DISPUTE,
  LENS_METHODOLOGY,
  __companionsTest__,
} from "./publisher.js";

const {
  runCompanion,
  toBytes32Hex,
  trackRecordPublishArgs,
  disputePublishArgs,
  methodologyPublishArgs,
} = __companionsTest__;

// ===========================================================================
// Test doubles
// ===========================================================================

/** Build a fake oracle. Each test customizes per-call behavior. */
function makeFakeOracle(opts: {
  existingHash?: string;
  getReportHashThrows?: boolean;
  estimateGasThrows?: boolean;
  publishThrows?: boolean;
  txHash?: string;
}): {
  oracle: any;
  calls: { getReportHash: number; estimate: number; publish: number };
} {
  const calls = { getReportHash: 0, estimate: 0, publish: 0 };

  const publishFn: any = async (..._args: any[]) => {
    calls.publish++;
    if (opts.publishThrows) throw new Error("tx send failed");
    return {
      hash: opts.txHash ?? "0xtxhash",
      wait: async (_n: number) => ({ status: 1 }),
    };
  };
  publishFn.estimateGas = async (..._args: any[]) => {
    calls.estimate++;
    if (opts.estimateGasThrows) throw new Error("execution reverted");
    return 50_000n;
  };

  const oracle = {
    getReportHash: async (_id: string) => {
      calls.getReportHash++;
      if (opts.getReportHashThrows) throw new Error("rpc unavailable");
      return [
        opts.existingHash ?? ethers.ZeroHash,
        "0x00000000",
        0n,
      ] as const;
    },
    publishReportHash: publishFn,
  };

  return { oracle, calls };
}

// nonceManager.getCurrentNonce calls provider.getTransactionCount; fake it.
const fakeProvider = {
  getTransactionCount: async (_addr: string, _tag: string) => 42,
} as unknown as ethers.JsonRpcProvider;
const fakeWallet = { address: "0x0000000000000000000000000000000000000001" } as ethers.Wallet;

const baseConfig = { dryRun: false } as any;
const dryRunConfig = { dryRun: true } as any;

// A real reportHash-shaped value
const HASH_A = "0x" + "a".repeat(64);
const HASH_B = "0x" + "b".repeat(64);
const ENTITY = "0x" + "1".repeat(64);

// ===========================================================================
// runCompanion — branch coverage
// ===========================================================================

describe("runCompanion — branch coverage", () => {
  it("first-write path: existing=Zero → submits tx, returns tx hash", async () => {
    const { oracle, calls } = makeFakeOracle({ txHash: "0xfeedbeef" });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, "0xfeedbeef");
    assert.equal(calls.getReportHash, 1);
    assert.equal(calls.estimate, 1);
    assert.equal(calls.publish, 1);
  });

  it("idempotent path: existing=same → returns existing hash, no publish", async () => {
    const { oracle, calls } = makeFakeOracle({ existingHash: HASH_A });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, HASH_A);
    assert.equal(calls.publish, 0);
  });

  it("idempotent path is case-insensitive on hex comparison", async () => {
    const { oracle, calls } = makeFakeOracle({ existingHash: HASH_A.toUpperCase() });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A.toLowerCase(), LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got?.toLowerCase(), HASH_A.toLowerCase());
    assert.equal(calls.publish, 0);
  });

  it("collision path: existing=different → returns null, no publish", async () => {
    const { oracle, calls } = makeFakeOracle({ existingHash: HASH_B });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.publish, 0);
    assert.equal(calls.estimate, 0);
  });

  it("DRY_RUN path: returns null, no estimate, no publish", async () => {
    const { oracle, calls } = makeFakeOracle({});
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", dryRunConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.getReportHash, 1);
    assert.equal(calls.estimate, 0);
    assert.equal(calls.publish, 0);
  });

  it("DRY_RUN still respects collision refusal (collision wins over dry-run skip)", async () => {
    const { oracle, calls } = makeFakeOracle({ existingHash: HASH_B });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", dryRunConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.publish, 0);
  });

  it("getReportHash failure: returns null, no publish", async () => {
    const { oracle, calls } = makeFakeOracle({ getReportHashThrows: true });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.publish, 0);
  });

  it("estimateGas failure: returns null, no publish", async () => {
    const { oracle, calls } = makeFakeOracle({ estimateGasThrows: true });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.estimate, 1);
    assert.equal(calls.publish, 0);
  });

  it("publish failure: returns null", async () => {
    const { oracle, calls } = makeFakeOracle({ publishThrows: true });
    const got = await runCompanion(
      oracle, ENTITY, HASH_A, LENS_TRACK_RECORD, "track_record",
      fakeProvider, fakeWallet, "base", baseConfig,
    );
    assert.equal(got, null);
    assert.equal(calls.publish, 1);
  });
});

// ===========================================================================
// toBytes32Hex — input shape coverage
// ===========================================================================

describe("toBytes32Hex", () => {
  it("accepts 64-hex-char string without 0x prefix and prepends 0x lowercase", () => {
    const got = toBytes32Hex("a".repeat(64));
    assert.equal(got, "0x" + "a".repeat(64));
  });

  it("accepts 0x-prefixed input and lowercases", () => {
    const got = toBytes32Hex("0X" + "F".repeat(64));
    assert.equal(got, "0x" + "f".repeat(64));
  });

  it("throws on empty input", () => {
    assert.throws(() => toBytes32Hex(""), /empty content_hash/);
  });

  it("throws on wrong length", () => {
    assert.throws(() => toBytes32Hex("0xabc"), /must be 32 bytes hex/);
  });

  it("throws on non-hex characters", () => {
    assert.throws(() => toBytes32Hex("z".repeat(64)), /not valid hex/);
  });
});

// ===========================================================================
// LENS constants — pinned values
// ===========================================================================

describe("LENS constants", () => {
  it("track_record lens is 0x00000100", () => assert.equal(LENS_TRACK_RECORD, "0x00000100"));
  it("dispute lens is 0x00000200",      () => assert.equal(LENS_DISPUTE,      "0x00000200"));
  it("methodology lens is 0x00000300",  () => assert.equal(LENS_METHODOLOGY,  "0x00000300"));
});

// ===========================================================================
// Wrapper integration via publish-args extractors
// Verifies each domain wrapper picks the right entityId (matching Day 1
// golden vectors), the right reportHash (toBytes32Hex of content_hash),
// and the right lens. Pulled from docs/oracle_option_c_golden_vectors.json.
// ===========================================================================

describe("trackRecordPublishArgs (SVB/USDC golden vector)", () => {
  it("entityId matches §11 Q2 worked example, lens = 0x00000100", () => {
    const args = trackRecordPublishArgs({
      entry_id: "01234567-89ab-cdef-0123-456789abcdef",
      entity_slug: "usdc",
      trigger_kind: "divergence",
      triggered_at: 1678512300,
      content_hash: "a".repeat(64),
    });
    assert.equal(args.entityId, "0xd043880c659392fb6a7d471906f334fce5175fb349ca646cb270033f81dbba4c");
    assert.equal(args.reportHash, "0x" + "a".repeat(64));
    assert.equal(args.lensId, LENS_TRACK_RECORD);
  });
});

describe("disputePublishArgs (golden vector: dispute A submission)", () => {
  it("entityId matches §11 Q2 worked example, lens = 0x00000200", () => {
    const args = disputePublishArgs({
      transition_id: "fedcba98-7654-3210-fedc-ba9876543210",
      dispute_id: "11111111-1111-1111-1111-111111111111",
      transition_kind: "submission",
      transition_index: 0,
      content_hash: "b".repeat(64),
    });
    assert.equal(args.entityId, "0x5f3101799bb86014467421ea710b260116b6353a9dc45a979d15192edf776cd8");
    assert.equal(args.reportHash, "0x" + "b".repeat(64));
    assert.equal(args.lensId, LENS_DISPUTE);
  });
});

describe("methodologyPublishArgs (lens_registry_v1 anchor)", () => {
  it("entityId matches §11 Q3 first-commit anchor, lens = 0x00000300", () => {
    const args = methodologyPublishArgs({
      methodology_id: "lens_registry_v1",
      content_hash: "c".repeat(64),
    });
    assert.equal(args.entityId, "0x54ab550521b1ed07db401b7931e85b9123033df6fbf195c91fe35b8e47474cf2");
    assert.equal(args.reportHash, "0x" + "c".repeat(64));
    assert.equal(args.lensId, LENS_METHODOLOGY);
  });
});
