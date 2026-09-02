import type { ValidateFunction } from "ajv";
import { describe, expect, it } from "vitest";

import {
  formatErrors,
  validateBridgeMessage,
  validateConsistencyCheckSet,
  validateFloorLevels,
  validateLayerStats,
  validateMarkupSidecar,
  validateNdjDocument,
  validateNdjEntity,
  validateTagsSidecar,
} from "../src/validate";
import { listExamples, loadExample } from "./helpers";

interface ExampleCase {
  validate: ValidateFunction<unknown>;
  /** `true` when the document must validate, `false` when it must be refused. */
  valid: boolean;
  /** Why the example exists. Shown in the test name. */
  reason: string;
}

/**
 * Every file under `examples/` is listed here with the schema it belongs to and
 * whether it must pass. A file that is added without an entry fails the suite,
 * so an example can never silently go unchecked.
 */
const CASES: Record<string, ExampleCase> = {
  "f06.ndj.json": {
    validate: validateNdjDocument,
    valid: true,
    reason: "small structural plan: four columns, beam centerlines, tags, one INSERT, one HATCH",
  },
  "layer-stats.f06.json": {
    validate: validateLayerStats,
    valid: true,
    reason: "crosscheck statistics for the same drawing",
  },
  "entity.line.json": {
    validate: validateNdjEntity,
    valid: true,
    reason: "single entity validated on its own, as the NDJSON stream reader does",
  },
  "entity.bad-missing-handle.json": {
    validate: validateNdjEntity,
    valid: false,
    reason: "provenance without a handle: evidence could never be resolved (CLAUDE.md rule 6)",
  },
  "entity.bad-unknown-type.json": {
    validate: validateNdjEntity,
    valid: false,
    reason: "entity type outside the closed v0 set",
  },
  "levels.ok.json": {
    validate: validateFloorLevels,
    valid: true,
    reason: "two floors with all four ADR-0003 height fields resolved separately",
  },
  "levels.bad-ch-eq-sl.json": {
    validate: validateConsistencyCheckSet,
    valid: false,
    reason: "ADR-0003 proof: an equality check between the ceiling height and a structural level",
  },
  "consistency.ok.json": {
    validate: validateConsistencyCheckSet,
    valid: true,
    reason:
      "same-basis equalities plus the cross-basis inequality ADR-0003 permits, plus the " +
      "addendum's CH<->CH equality against a CEILING_PLAN source",
  },
  "consistency.bad.json": {
    validate: validateConsistencyCheckSet,
    valid: false,
    reason: "cross-basis equality between the finished floor level and the structural level",
  },
  "consistency.bad-ch-eq-no-ceiling-plan.json": {
    validate: validateConsistencyCheckSet,
    valid: false,
    reason:
      "ADR-0003 addendum proof: CH<->CH equality is still rejected when neither source is " +
      "CEILING_PLAN",
  },
  "markup.json": { validate: validateMarkupSidecar, valid: true, reason: "cloud, arrow and note" },
  "tags.json": {
    validate: validateTagsSidecar,
    valid: true,
    reason: "automatic tag plus a user override that keeps the machine answer",
  },
  "bridge.ready.json": { validate: validateBridgeMessage, valid: true, reason: "viewer handshake" },
  "bridge.load.json": { validate: validateBridgeMessage, valid: true, reason: "load a GLB model" },
  "bridge.select.json": {
    validate: validateBridgeMessage,
    valid: true,
    reason: "push the 2D selection into the panel",
  },
  "bridge.colorize.json": {
    validate: validateBridgeMessage,
    valid: true,
    reason: "confidence overlay",
  },
  "bridge.camera.json": {
    validate: validateBridgeMessage,
    valid: true,
    reason: "set a section plane",
  },
  "bridge.selected.json": {
    validate: validateBridgeMessage,
    valid: true,
    reason: "selection reported back from the panel",
  },
  "bridge.error.json": {
    validate: validateBridgeMessage,
    valid: true,
    reason: "coded error instead of an exception across the iframe boundary",
  },
  "bridge.bad-unknown-type.json": {
    validate: validateBridgeMessage,
    valid: false,
    reason: "message type outside the ADR-0004 list",
  },
};

describe("examples", () => {
  it("every example file is covered by a case", () => {
    expect(listExamples()).toEqual(Object.keys(CASES).sort());
  });

  for (const [name, { validate, valid, reason }] of Object.entries(CASES)) {
    it(`${name} ${valid ? "validates" : "is rejected"} (${reason})`, () => {
      const data = loadExample(name);
      const result = validate(data);
      if (valid && !result) {
        throw new Error(
          `${name} should validate but did not: ${JSON.stringify(formatErrors(validate.errors), null, 2)}`
        );
      }
      expect(result).toBe(valid);
    });
  }
});
