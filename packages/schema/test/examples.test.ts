import type { ValidateFunction } from "ajv";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

import crosscheckReportSchema from "../src/stats/crosscheck-report.schema.json";
import {
  formatErrors,
  validateBridgeMessage,
  validateChange,
  validateCluster,
  validateClustersSidecar,
  validateCompareSetSummary,
  validateConsistencyCheckSet,
  validateFloorLevels,
  validateLayerStats,
  validateMarkupSidecar,
  validateNdjDocument,
  validateNdjEntity,
  validateRevisionTruth,
  validateRun,
  validateSheetFrame,
  validateSheetPair,
  validateTagsSidecar,
} from "../src/validate";
import { listExamples, loadExample } from "./helpers";

// `CrosscheckReport` (see test/crosscheck-report.test.ts for the full story) is
// not registered in src/schemas.ts/src/validate.ts -- that file is outside this
// task's "Files you own" glob (brief W3-08) -- so its example is checked here
// with its own throwaway ajv instance instead of the shared `validateXxx` export
// every other case in this table uses.
const crosscheckReportAjv = new Ajv2020({ strict: true, allErrors: true });
addFormats(crosscheckReportAjv);
const validateCrosscheckReport = crosscheckReportAjv.compile(crosscheckReportSchema);

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
  "crosscheck-report.f06.json": {
    validate: validateCrosscheckReport,
    valid: true,
    reason:
      "a real report from the engine's compare(), ezdxf vs. a perturbed mlightcad copy on F06 " +
      "(one RED count_by_type difference on X-GRID)",
  },
  "compare.sheet-frame.json": {
    validate: validateSheetFrame,
    valid: true,
    reason: "one recognised title block: A-101 at 1:100, with the raw ATTRIB values kept as evidence",
  },
  "compare.sheet-pair.json": {
    validate: validateSheetPair,
    valid: true,
    reason: "A-101 matched by number, with both frame summaries embedded as the pairs list sends them",
  },
  "compare.change.json": {
    validate: validateChange,
    valid: true,
    reason: "a door block moved 1,250mm east, with both sides' provenance and its compare-DXF handles",
  },
  "compare.cluster.json": {
    validate: validateCluster,
    valid: true,
    reason: "the cloud mark around that move: four bulged vertices and the numbered badge",
  },
  "compare.run.json": {
    validate: validateRun,
    valid: true,
    reason: "one export: a single markup DWG written by ZWCAD into 출력/2026-09-04",
  },
  "compare.clusters-sidecar.json": {
    validate: validateClustersSidecar,
    valid: true,
    reason:
      "a whole clusters.json: one cluster, one clustered change and one minor change that is " +
      "counted but not clustered",
  },
  "compare.compare-set.json": {
    validate: validateCompareSetSummary,
    valid: true,
    reason: "the screen A/B summary of a finished comparison, ZWCAD available on both sides",
  },
  "compare.truth.json": {
    validate: validateRevisionTruth,
    valid: true,
    reason: "a synthetic scenario's expectations: a planted move, a folded layer change, a clean region",
  },
  "compare.bad-change-no-provenance.json": {
    validate: validateChange,
    valid: false,
    reason: "a change with no provenance: the marked-up entity could never be traced back (CLAUDE.md rule 5)",
  },
  "compare.bad-change-unknown-kind.json": {
    validate: validateChange,
    valid: false,
    reason: "`kind: \"recolored\"` -- outside the closed set the compare DXF knows how to draw",
  },
  "compare.bad-cluster-decision-typo.json": {
    validate: validateCluster,
    valid: false,
    reason: "`decision: \"aproved\"` -- a typo must not silently read as 미검토 and drop the cluster from the export",
  },
  "compare.bad-sidecar-dangling-handle.json": {
    validate: validateClustersSidecar,
    valid: true,
    reason:
      "schema-valid on purpose: `handle_to_cluster` points at a cluster that is not in the file, " +
      "which 2020-12 cannot express -- clustersSidecarIntegrityFailures rejects it, see compare.test.ts",
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
