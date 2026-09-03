import { describe, expect, it } from "vitest";

import type { ConsistencyCheck } from "../src/validate";
import {
  formatErrors,
  validateConsistencyCheck,
  validateConsistencyCheckSet,
  validateFloorLevels,
  validateLevelObservation,
} from "../src/validate";
import { clone, loadExample } from "./helpers";

function check(overrides: Partial<ConsistencyCheck>): unknown {
  return {
    id: "PROBE",
    left_kind: "SL",
    right_kind: "SL",
    operator: "EQ",
    tolerance_mm: 5,
    ...overrides,
  };
}

/**
 * ADR-0003. The rule is not a lint and not a convention: the schema refuses to
 * describe a forbidden comparison, so no rule file, no generated model and no
 * hand-written check can express one.
 */
describe("ADR-0003 height comparison rules", () => {
  const sameBasis = ["SL", "FL", "FLOOR_HEIGHT"] as const;

  for (const kind of sameBasis) {
    it(`allows an EQ check between two ${kind} readings`, () => {
      expect(validateConsistencyCheck(check({ left_kind: kind, right_kind: kind }))).toBe(true);
    });
  }

  for (const other of sameBasis) {
    it(`rejects an EQ check with CH on the left and ${other} on the right`, () => {
      expect(validateConsistencyCheck(check({ left_kind: "CH", right_kind: other }))).toBe(false);
    });

    it(`rejects an EQ check with ${other} on the left and CH on the right`, () => {
      expect(validateConsistencyCheck(check({ left_kind: other, right_kind: "CH" }))).toBe(false);
    });
  }

  it("rejects an EQ check between two CH readings as well", () => {
    // The brief enumerates SL, FL and FLOOR_HEIGHT as the only bases that may be
    // compared with EQ. Two ceiling heights coming from different tables are
    // compared with an inequality band instead (see consistency.ok.json) --
    // unless one of them is CEILING_PLAN (ADR-0003 addendum, below).
    expect(validateConsistencyCheck(check({ left_kind: "CH", right_kind: "CH" }))).toBe(false);
  });

  it("rejects an EQ check between two CH readings sourced from tables (no CEILING_PLAN)", () => {
    expect(
      validateConsistencyCheck(
        check({
          left_kind: "CH",
          right_kind: "CH",
          left_source: "LEVEL_TABLE",
          right_source: "FINISH_SCHEDULE",
        })
      )
    ).toBe(false);
  });

  // ADR-0003 addendum (2026-09-03): a ceiling plan drawing that labels its own
  // CH may be checked for equality against the level/finish-schedule CH.
  it("allows an EQ check between two CH readings when the left source is CEILING_PLAN", () => {
    expect(
      validateConsistencyCheck(
        check({
          left_kind: "CH",
          right_kind: "CH",
          left_source: "CEILING_PLAN",
          right_source: "LEVEL_TABLE",
        })
      )
    ).toBe(true);
  });

  it("allows an EQ check between two CH readings when the right source is CEILING_PLAN", () => {
    expect(
      validateConsistencyCheck(
        check({
          left_kind: "CH",
          right_kind: "CH",
          left_source: "FINISH_SCHEDULE",
          right_source: "CEILING_PLAN",
        })
      )
    ).toBe(true);
  });

  it("does not widen the CEILING_PLAN exception to a CH vs. a structural basis", () => {
    // The addendum permits CH<->CH only. CEILING_PLAN as a source is not by
    // itself enough to license comparing CH against SL/FL/FLOOR_HEIGHT.
    expect(
      validateConsistencyCheck(
        check({
          left_kind: "CH",
          right_kind: "SL",
          left_source: "CEILING_PLAN",
          right_source: "ELEVATION",
        })
      )
    ).toBe(false);
  });

  it("rejects a cross-basis EQ check that does not involve CH", () => {
    expect(validateConsistencyCheck(check({ left_kind: "FL", right_kind: "SL" }))).toBe(false);
  });

  for (const operator of ["LT", "LE", "GT", "GE"] as const) {
    it(`allows a ${operator} check between CH and FLOOR_HEIGHT`, () => {
      expect(
        validateConsistencyCheck(
          check({
            left_kind: "CH",
            right_kind: "FLOOR_HEIGHT",
            operator,
            tolerance_mm: 0,
            left_offset_mm: 250,
          })
        )
      ).toBe(true);
    });
  }

  it("allows the ADR-0003 cross-basis inequality with slab and finish added on the left", () => {
    const ok = check({
      id: "CH_FITS_UNDER_STOREY",
      left_kind: "CH",
      right_kind: "FLOOR_HEIGHT",
      operator: "LT",
      tolerance_mm: 0,
      left_offset_mm: 250,
    });
    expect(validateConsistencyCheck(ok)).toBe(true);
  });

  it("rejects the whole check set when a single definition breaks the rule", () => {
    const set = loadExample("levels.bad-ch-eq-sl.json");
    expect(validateConsistencyCheckSet(set)).toBe(false);
    const failures = formatErrors(validateConsistencyCheckSet.errors);
    // The first check in the file is legal; only the second one is at fault.
    expect(failures.some((failure) => failure.path.startsWith("/checks/1"))).toBe(true);
    expect(failures.every((failure) => !failure.path.startsWith("/checks/0"))).toBe(true);
  });

  it("keeps the four height fields separate on a floor", () => {
    const doc = loadExample("levels.ok.json") as {
      floors: Record<string, unknown>[];
    };
    expect(validateFloorLevels(doc)).toBe(true);
    const third = doc.floors[0]!;
    expect(third.sl_mm).toBe(9000);
    expect(third.fl_mm).toBe(9050);
    expect(third.floor_height_mm).toBe(3300);
    expect(third.ch_mm).toBe(2700);
    // The only legal relation across bases is the inequality of ADR-0003.
    const slab = 200;
    const floorFinish = 50;
    expect(
      (third.ch_mm as number) + slab + floorFinish < (third.floor_height_mm as number)
    ).toBe(true);
  });

  it("refuses a ceiling height derived from a structural level difference", () => {
    const doc = clone(
      loadExample("levels.ok.json") as { floors: Record<string, unknown>[] }
    );
    doc.floors[0]!.ch_method = "DERIVED_SL_DIFF";
    delete doc.floors[0]!.ch_source_observation_id;
    expect(validateFloorLevels(doc)).toBe(false);
  });

  it("requires the source observation of a height that claims to have been read", () => {
    const doc = clone(
      loadExample("levels.ok.json") as { floors: Record<string, unknown>[] }
    );
    delete doc.floors[0]!.sl_source_observation_id;
    expect(validateFloorLevels(doc)).toBe(false);
  });

  it("accepts each of the four kinds on a level observation", () => {
    for (const kind of ["SL", "FL", "FLOOR_HEIGHT", "CH"] as const) {
      const observation = {
        id: "3QDKA01V7Z92XDAFB342P3RS7T",
        kind,
        value_mm: 2700,
        source: "USER",
        evidence: [],
        confidence: 1,
        raw_text: "",
      };
      expect(validateLevelObservation(observation)).toBe(true);
    }
  });

  it("rejects a level observation whose kind is not one of the four", () => {
    expect(
      validateLevelObservation({
        id: "3QDKA01V7Z92XDAFB342P3RS7T",
        kind: "CEILING",
        value_mm: 2700,
        source: "USER",
        evidence: [],
        confidence: 1,
        raw_text: "",
      })
    ).toBe(false);
  });

  it("requires evidence on every observation that was not typed by a user", () => {
    expect(
      validateLevelObservation({
        id: "3QDKA01V7Z92XDAFB342P3RS7T",
        kind: "CH",
        value_mm: 2700,
        source: "LEVEL_TABLE",
        evidence: [],
        confidence: 0.8,
        raw_text: "2,700",
      })
    ).toBe(false);
  });
});
