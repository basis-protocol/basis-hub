/**
 * Tests for keeper/optionC_keys.ts — TypeScript port of the canonical
 * entityId computation. Loads docs/oracle_option_c_golden_vectors.json
 * (single source of truth shared with tests/test_oracle_keys.py) and
 * asserts byte-exact match per vector.
 *
 * Run: `npx tsx --test keeper/optionC_keys.test.ts`
 *
 * Failure messages include label + expected + actual hex so a
 * divergence between the TS port and the canonical JSON is
 * immediately legible in CI output.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  DOMAIN_DISPUTE,
  DOMAIN_METHODOLOGY,
  DOMAIN_TRACK_RECORD,
  disputeEntityId,
  methodologyEntityId,
  trackRecordEntityId,
  __test__,
} from "./optionC_keys.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const GOLDEN_PATH = resolve(__dirname, "../docs/oracle_option_c_golden_vectors.json");

interface TrackVector {
  label: string;
  entity_slug: string;
  trigger_kind: string;
  triggered_at_unix: number;
  triggered_at_iso: string;
  expected_entity_id: string;
}
interface DisputeVector {
  label: string;
  dispute_id: string;
  transition_kind: string;
  transition_index: number;
  expected_entity_id: string;
}
interface MethodologyVector {
  label: string;
  methodology_id: string;
  expected_entity_id: string;
}
interface GoldenFile {
  track_record: TrackVector[];
  dispute: DisputeVector[];
  methodology: MethodologyVector[];
  selectors: Record<string, string>;
}

const golden: GoldenFile = JSON.parse(readFileSync(GOLDEN_PATH, "utf-8"));

function fmtFail(label: string, expected: string, got: string): string {
  return `\n  label:    ${label}\n  expected: ${expected}\n  got:      ${got}`;
}

// ===========================================================================
// Track-record vectors (5)
// ===========================================================================

describe("trackRecordEntityId — golden vectors", () => {
  for (const vec of golden.track_record) {
    it(vec.label, () => {
      const got = trackRecordEntityId(
        vec.entity_slug,
        vec.trigger_kind,
        vec.triggered_at_unix,
      );
      assert.equal(got, vec.expected_entity_id, fmtFail(vec.label, vec.expected_entity_id, got));
    });
  }
});

// ===========================================================================
// Dispute vectors (5)
// ===========================================================================

describe("disputeEntityId — golden vectors", () => {
  for (const vec of golden.dispute) {
    it(vec.label, () => {
      const got = disputeEntityId(
        vec.dispute_id,
        vec.transition_kind,
        vec.transition_index,
      );
      assert.equal(got, vec.expected_entity_id, fmtFail(vec.label, vec.expected_entity_id, got));
    });
  }
});

// ===========================================================================
// Methodology vectors (5)
// ===========================================================================

describe("methodologyEntityId — golden vectors", () => {
  for (const vec of golden.methodology) {
    it(vec.label, () => {
      const got = methodologyEntityId(vec.methodology_id);
      assert.equal(got, vec.expected_entity_id, fmtFail(vec.label, vec.expected_entity_id, got));
    });
  }
});

// ===========================================================================
// Selector helper (8 cross-reference values)
// ===========================================================================

describe("selector4 — bytes4(keccak256(utf8(value)))", () => {
  for (const [name, expectedHex] of Object.entries(golden.selectors)) {
    if (name.startsWith("_")) continue; // skip _comment field
    it(`selector(${name})`, () => {
      const got = "0x" + Buffer.from(__test__.selector4(name)).toString("hex");
      assert.equal(got, expectedHex, fmtFail(`selector(${name})`, expectedHex, got));
    });
  }
});

// ===========================================================================
// triggered_at coercion — Date / ISO string / number yield same hex
// ===========================================================================

describe("trackRecordEntityId — triggered_at coercion", () => {
  it("Date / ISO string / number all produce same entityId (SVB/USDC vector)", () => {
    const vec = golden.track_record[0]; // SVB/USDC depeg
    const viaInt = trackRecordEntityId(vec.entity_slug, vec.trigger_kind, vec.triggered_at_unix);
    const viaIso = trackRecordEntityId(vec.entity_slug, vec.trigger_kind, vec.triggered_at_iso);
    const viaDate = trackRecordEntityId(
      vec.entity_slug, vec.trigger_kind, new Date(vec.triggered_at_unix * 1000),
    );
    assert.equal(viaInt, vec.expected_entity_id);
    assert.equal(viaIso, vec.expected_entity_id);
    assert.equal(viaDate, vec.expected_entity_id);
  });
});

// ===========================================================================
// Domain-prefix collision separation
// ===========================================================================

describe("Domain-prefix collision separation", () => {
  it("DOMAIN_* constants are distinct byte sequences", () => {
    const a = Buffer.from(DOMAIN_TRACK_RECORD).toString("hex");
    const b = Buffer.from(DOMAIN_DISPUTE).toString("hex");
    const c = Buffer.from(DOMAIN_METHODOLOGY).toString("hex");
    assert.notEqual(a, b);
    assert.notEqual(b, c);
    assert.notEqual(a, c);
  });

  it("Same string fed to all three commit types yields three distinct entityIds", () => {
    const s = "lens_registry_v1";
    const meth = methodologyEntityId(s);
    const track = trackRecordEntityId(s, "manual", 0);
    const disp = disputeEntityId(s, "submission", 0);
    const set = new Set([meth, track, disp]);
    assert.equal(
      set.size, 3,
      `Domain prefixes failed to separate collisions:\n  meth=${meth}\n  track=${track}\n  disp=${disp}`,
    );
  });
});

// ===========================================================================
// uint64BE bounds
// ===========================================================================

describe("uint64BE bounds", () => {
  it("encodes 0 as 8 zero bytes", () => {
    const got = Buffer.from(__test__.uint64BE(0)).toString("hex");
    assert.equal(got, "0000000000000000");
  });
  it("encodes max uint64", () => {
    const got = Buffer.from(__test__.uint64BE(0xFFFFFFFFFFFFFFFFn)).toString("hex");
    assert.equal(got, "ffffffffffffffff");
  });
  it("rejects negative values", () => {
    assert.throws(() => __test__.uint64BE(-1), RangeError);
  });
  it("rejects values >= 2^64", () => {
    assert.throws(() => __test__.uint64BE(0x10000000000000000n), RangeError);
  });
});

// ===========================================================================
// Sanity: golden JSON shape
// ===========================================================================

describe("Golden JSON sanity", () => {
  it("contains 5 vectors per type (15 total)", () => {
    assert.equal(golden.track_record.length, 5);
    assert.equal(golden.dispute.length, 5);
    assert.equal(golden.methodology.length, 5);
  });

  it("lens_registry_v1 anchor matches §11 Q3 first-commit hex", () => {
    // If this hex changes, runbook §5.1 mainnet sequence breaks.
    const lens = golden.methodology.find((v) => v.methodology_id === "lens_registry_v1");
    assert.ok(lens, "lens_registry_v1 vector missing from golden JSON");
    assert.equal(
      lens.expected_entity_id,
      "0x54ab550521b1ed07db401b7931e85b9123033df6fbf195c91fe35b8e47474cf2",
    );
  });

  it("returned entity IDs are 0x-prefixed lowercase 32-byte hex", () => {
    const allHexes = [
      ...golden.track_record.map((v) => v.expected_entity_id),
      ...golden.dispute.map((v) => v.expected_entity_id),
      ...golden.methodology.map((v) => v.expected_entity_id),
    ];
    for (const h of allHexes) {
      assert.match(h, /^0x[0-9a-f]{64}$/);
    }
  });
});
