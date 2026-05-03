/**
 * Tests for keeper/companions_cycle.ts — runCompanionStep + URL builders
 * + HTTP helpers (fetchAdminEndpoint, markCommitted).
 *
 * Covers the orchestration that wraps Day 2.2's Companion helpers:
 *   - Pending fetch + per-entry iteration + mark-committed dispatch
 *   - Stats tallying (success/dry_run/skipped/error)
 *   - Per-entry exception isolation
 *   - Batch size cap
 *   - URL path correctness for each domain (matches /api/ops/* hub surface)
 *   - HTTP helper auth header (x-admin-key, NOT Authorization: Bearer)
 *
 * Run: `npx tsx --test keeper/cycle.test.ts`
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { ethers } from "ethers";

import {
  runCompanionStep,
  trackRecordStepArgs,
  disputeStepArgs,
  methodologyStepArgs,
  fetchAdminEndpoint,
  markCommitted,
  type CompanionStepArgs,
} from "./companions_cycle.js";

// ===========================================================================
// Test doubles
// ===========================================================================

const fakeProvider = {} as ethers.JsonRpcProvider;
const fakeWallet = { address: "0x0000000000000000000000000000000000000001" } as ethers.Wallet;

interface FakeEntry {
  id: string;
  content_hash: string;
}

function makeArgs(opts: {
  pending: FakeEntry[];
  publishReturns: (string | null)[]; // per-entry tx hash or null
  dryRun?: boolean;
  fetchThrows?: boolean;
  markCommittedThrows?: boolean;
}): {
  args: CompanionStepArgs<FakeEntry>;
  calls: { fetched: string[]; markCommitted: { url: string; body: any }[]; published: number };
} {
  const calls = { fetched: [] as string[], markCommitted: [] as any[], published: 0 };

  const args: CompanionStepArgs<FakeEntry> = {
    stepLabel: "step T",
    domain: "track_record",
    apiUrl: "https://hub.test",
    adminKey: "test-admin-key",
    chainKey: "base",
    oracleAddress: "0xORACLE",
    provider: fakeProvider,
    wallet: fakeWallet,
    config: { dryRun: opts.dryRun ?? false } as any,
    pendingUrl: (apiUrl, chainKey) => `${apiUrl}/path/${chainKey}`,
    markCommittedUrl: (apiUrl, entry, chainKey) => `${apiUrl}/commit/${entry.id}/${chainKey}`,
    entryIdField: (e) => e.id,
    publishFn: async () => {
      const r = opts.publishReturns[calls.published] ?? null;
      calls.published++;
      return r;
    },
    deps: {
      fetchFn: async (url) => {
        calls.fetched.push(url);
        if (opts.fetchThrows) throw new Error("fetch boom");
        return opts.pending;
      },
      markCommittedFn: async (url, _key, body) => {
        calls.markCommitted.push({ url, body });
        if (opts.markCommittedThrows) throw new Error("mark-committed boom");
      },
    },
  };

  return { args, calls };
}

// ===========================================================================
// runCompanionStep — orchestration coverage
// ===========================================================================

describe("runCompanionStep", () => {
  it("happy path: 2 pending, both publish, both mark-committed", async () => {
    const { args, calls } = makeArgs({
      pending: [{ id: "e1", content_hash: "" }, { id: "e2", content_hash: "" }],
      publishReturns: ["0xTX1", "0xTX2"],
    });
    const stats = await runCompanionStep(args);
    assert.equal(stats.pending, 2);
    assert.equal(stats.success, 2);
    assert.equal(stats.dry_run, 0);
    assert.equal(stats.skipped, 0);
    assert.equal(stats.error, 0);
    assert.equal(calls.markCommitted.length, 2);
    assert.deepEqual(calls.markCommitted[0].body, { tx_hash: "0xTX1" });
    assert.deepEqual(calls.markCommitted[1].body, { tx_hash: "0xTX2" });
  });

  it("dry-run: pending entries counted as dry_run, no mark-committed", async () => {
    const { args, calls } = makeArgs({
      pending: [{ id: "e1", content_hash: "" }, { id: "e2", content_hash: "" }],
      publishReturns: [null, null],   // companion returns null in dry-run
      dryRun: true,
    });
    const stats = await runCompanionStep(args);
    assert.equal(stats.dry_run, 2);
    assert.equal(stats.success, 0);
    assert.equal(calls.markCommitted.length, 0);
  });

  it("collision/skip: publishFn returns null without dryRun → skipped++", async () => {
    const { args, calls } = makeArgs({
      pending: [{ id: "e1", content_hash: "" }],
      publishReturns: [null],
    });
    const stats = await runCompanionStep(args);
    assert.equal(stats.skipped, 1);
    assert.equal(stats.success, 0);
    assert.equal(calls.markCommitted.length, 0);
  });

  it("mark-committed failure counts as error; tx still on chain", async () => {
    const { args, calls } = makeArgs({
      pending: [{ id: "e1", content_hash: "" }],
      publishReturns: ["0xTX1"],
      markCommittedThrows: true,
    });
    const stats = await runCompanionStep(args);
    assert.equal(stats.error, 1);
    assert.equal(stats.success, 0);
    assert.equal(calls.markCommitted.length, 1); // attempted
  });

  it("fetch failure: returns empty stats, no exception", async () => {
    const { args, calls } = makeArgs({
      pending: [], publishReturns: [], fetchThrows: true,
    });
    const stats = await runCompanionStep(args);
    assert.equal(stats.pending, 0);
    assert.equal(stats.success, 0);
    assert.equal(calls.fetched.length, 1);
  });

  it("per-entry exception does not abort batch", async () => {
    const { args, calls } = makeArgs({
      pending: [
        { id: "e1", content_hash: "" },
        { id: "e2", content_hash: "" },
        { id: "e3", content_hash: "" },
      ],
      publishReturns: ["0xTX1", "0xTX3"], // e2 will throw via override below
    });
    let nth = 0;
    args.publishFn = async () => {
      nth++;
      if (nth === 2) throw new Error("publish boom");
      return nth === 1 ? "0xTX1" : "0xTX3";
    };
    const stats = await runCompanionStep(args);
    assert.equal(stats.pending, 3);
    assert.equal(stats.success, 2);
    assert.equal(stats.error, 1);
  });

  it("batch size cap of 50: 60 pending → only 50 processed", async () => {
    const pending: FakeEntry[] = [];
    const publishReturns: (string | null)[] = [];
    for (let i = 0; i < 60; i++) {
      pending.push({ id: `e${i}`, content_hash: "" });
      publishReturns.push(`0xTX${i}`);
    }
    const { args, calls } = makeArgs({ pending, publishReturns });
    const stats = await runCompanionStep(args);
    assert.equal(stats.pending, 60);
    assert.equal(stats.success, 50);
    assert.equal(calls.markCommitted.length, 50);
  });

  it("non-array pending response treated as empty", async () => {
    const { args } = makeArgs({ pending: [], publishReturns: [] });
    args.deps!.fetchFn = async () => ({ malformed: true } as any);
    const stats = await runCompanionStep(args);
    assert.equal(stats.pending, 0);
  });
});

// ===========================================================================
// URL builders — verify each domain's pendingUrl / markCommittedUrl match
// the corrected /api/ops/* surface verified in Day 2.1.
// ===========================================================================

describe("URL builders match /api/ops surface", () => {
  const common = {
    apiUrl: "https://hub.example",
    adminKey: "k",
    chainKey: "base" as const,
    oracleAddress: "0xORACLE",
    provider: fakeProvider,
    wallet: fakeWallet,
    config: { dryRun: false } as any,
  };

  it("track-record uses /track-record/pending-on-chain and /entries/{id}/committed/{chain}", () => {
    const args = trackRecordStepArgs(common);
    assert.equal(
      args.pendingUrl(common.apiUrl, "base"),
      "https://hub.example/api/ops/track-record/pending-on-chain?chain=base",
    );
    assert.equal(
      args.markCommittedUrl(common.apiUrl, { entry_id: "abc", entity_slug: "x", trigger_kind: "manual", triggered_at: 0, content_hash: "" }, "arbitrum"),
      "https://hub.example/api/ops/track-record/entries/abc/committed/arbitrum",
    );
    assert.equal(args.stepLabel, "step 8");
    assert.equal(args.domain, "track_record");
  });

  it("dispute uses /disputes/pending-on-chain and /transitions/{id}/committed/{chain}", () => {
    const args = disputeStepArgs(common);
    assert.equal(
      args.pendingUrl(common.apiUrl, "base"),
      "https://hub.example/api/ops/disputes/pending-on-chain?chain=base",
    );
    assert.equal(
      args.markCommittedUrl(common.apiUrl, { transition_id: "t1", dispute_id: "d", transition_kind: "submission", transition_index: 0, content_hash: "" }, "base"),
      "https://hub.example/api/ops/disputes/transitions/t1/committed/base",
    );
    assert.equal(args.stepLabel, "step 9");
    assert.equal(args.domain, "dispute");
  });

  it("methodology uses /methodology/pending-on-chain and /{id}/committed/{chain}", () => {
    const args = methodologyStepArgs(common);
    assert.equal(
      args.pendingUrl(common.apiUrl, "arbitrum"),
      "https://hub.example/api/ops/methodology/pending-on-chain?chain=arbitrum",
    );
    assert.equal(
      args.markCommittedUrl(common.apiUrl, { methodology_id: "lens_registry_v1", content_hash: "" }, "base"),
      "https://hub.example/api/ops/methodology/lens_registry_v1/committed/base",
    );
    assert.equal(args.stepLabel, "step 10");
    assert.equal(args.domain, "methodology");
  });
});

// ===========================================================================
// HTTP helpers — verify auth header + body shape via global fetch stub.
// ===========================================================================

describe("HTTP helpers", () => {
  function withFetchStub<T>(
    fn: (recorded: { url: string; init: any }[]) => Promise<T>,
    response: { ok: boolean; status?: number; body?: any; text?: string },
  ): Promise<T> {
    const recorded: { url: string; init: any }[] = [];
    const orig = globalThis.fetch;
    globalThis.fetch = (async (url: any, init: any) => {
      recorded.push({ url: String(url), init });
      return {
        ok: response.ok,
        status: response.status ?? (response.ok ? 200 : 500),
        json: async () => response.body ?? null,
        text: async () => response.text ?? JSON.stringify(response.body ?? null),
      } as Response;
    }) as any;
    return fn(recorded).finally(() => { globalThis.fetch = orig; });
  }

  it("fetchAdminEndpoint sends x-admin-key header (not Bearer)", async () => {
    await withFetchStub(async (recorded) => {
      const result = await fetchAdminEndpoint("https://h/api/ops/methodology/pending-on-chain?chain=base", "secret");
      assert.deepEqual(result, [{ methodology_id: "x" }]);
      assert.equal(recorded.length, 1);
      const headers = recorded[0].init.headers;
      assert.equal(headers["x-admin-key"], "secret");
      assert.equal(headers["accept"], "application/json");
      // Must not use Authorization: Bearer
      assert.equal(headers["authorization"], undefined);
      assert.equal(headers["Authorization"], undefined);
    }, { ok: true, body: [{ methodology_id: "x" }] });
  });

  it("fetchAdminEndpoint throws on non-2xx", async () => {
    await withFetchStub(async () => {
      await assert.rejects(
        () => fetchAdminEndpoint("https://h/u", "k"),
        /HTTP 401/,
      );
    }, { ok: false, status: 401, text: "Unauthorized" });
  });

  it("markCommitted POSTs JSON body with x-admin-key", async () => {
    await withFetchStub(async (recorded) => {
      await markCommitted("https://h/api/ops/methodology/x/committed/base", "secret", { tx_hash: "0xabc" });
      assert.equal(recorded.length, 1);
      assert.equal(recorded[0].init.method, "POST");
      assert.equal(recorded[0].init.headers["x-admin-key"], "secret");
      assert.equal(recorded[0].init.headers["content-type"], "application/json");
      assert.deepEqual(JSON.parse(recorded[0].init.body), { tx_hash: "0xabc" });
    }, { ok: true });
  });

  it("markCommitted throws on non-2xx", async () => {
    await withFetchStub(async () => {
      await assert.rejects(
        () => markCommitted("https://h/u", "k", { tx_hash: "0x1" }),
        /HTTP 404/,
      );
    }, { ok: false, status: 404, text: "Not Found" });
  });
});

// ===========================================================================
// Lens guarantee — sanity that no Companion step ever defaults to lens 0
// (would corrupt SII/PSI report path). Pinning the step labels ensures
// no future refactor silently changes the lens dispatch.
// ===========================================================================

describe("Step → domain → lens invariant", () => {
  const common = {
    apiUrl: "x", adminKey: "y", chainKey: "base" as const,
    oracleAddress: "0x0", provider: fakeProvider, wallet: fakeWallet,
    config: { dryRun: false } as any,
  };
  it("track-record step is bound to track_record domain (lens 0x00000100)", () => {
    assert.equal(trackRecordStepArgs(common).domain, "track_record");
  });
  it("dispute step is bound to dispute domain (lens 0x00000200)", () => {
    assert.equal(disputeStepArgs(common).domain, "dispute");
  });
  it("methodology step is bound to methodology domain (lens 0x00000300)", () => {
    assert.equal(methodologyStepArgs(common).domain, "methodology");
  });
});
