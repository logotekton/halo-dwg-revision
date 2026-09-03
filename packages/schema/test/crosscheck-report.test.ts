import { readFileSync } from "node:fs";
import path from "node:path";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

import crosscheckReportSchema from "../src/stats/crosscheck-report.schema.json";
import { loadExample, PACKAGE_ROOT } from "./helpers";

/**
 * `CrosscheckReport` (brief W3-08 goal 2, G0 follow-up 4) is unlike every
 * other schema in this package: its source of truth is not hand-authored
 * JSON Schema in `src/` -- it is generated from the engine's own pydantic
 * model (`engine/src/halo_engine/model/crosscheck.py`, via
 * `halo_engine.validate.crosscheck.report_schema_text()`), which
 * `engine/tests/validate/test_report_schema.py` already keeps in sync with
 * the model. `src/stats/crosscheck-report.schema.json` is a **byte-identical
 * copy** of that committed file, so this schema package's copy is
 * transitively proven equivalent to the pydantic model without either
 * language importing the other's toolchain -- see this task's report
 * "Decisions" for why a byte copy was chosen over re-authoring it in this
 * package's usual absolute-$ref dialect (docs/contracts/wave-3.md /
 * packages/schema/README.md conventions don't apply to a file this package
 * does not originate).
 *
 * This copy is not registered in `src/schemas.ts`/`src/validate.ts` (outside
 * this task's "Files you own" glob -- W3-08 brief) -- the TS codegen
 * (`gen/ts/stats/crosscheck-report.d.ts`) and Python codegen
 * (`gen/python/halo_schema/models/stats/crosscheck_report_schema.py`) both
 * discover it automatically by walking `src/**\/*.schema.json`, which is all
 * this item's Goal 2 asks for; a validated ajv instance and any
 * `drawing_file.parser_crosscheck` storage wiring is left to whichever task
 * owns that (G0 follow-up 4 names it separately from this one).
 */

const ENGINE_SCHEMA_PATH = path.join(
  PACKAGE_ROOT,
  "..",
  "..",
  "engine",
  "src",
  "halo_engine",
  "validate",
  "crosscheck_report.schema.json"
);

function compileCrosscheckReport() {
  const ajv = new Ajv2020({ strict: true, allErrors: true });
  addFormats(ajv);
  return ajv.compile(crosscheckReportSchema);
}

describe("CrosscheckReport schema (packages/schema copy)", () => {
  it("is byte-identical to the engine's committed schema", () => {
    const engineSchemaText = readFileSync(ENGINE_SCHEMA_PATH, "utf8");
    const packageSchemaText = readFileSync(
      path.join(PACKAGE_ROOT, "src", "stats", "crosscheck-report.schema.json"),
      "utf8"
    );
    expect(packageSchemaText).toBe(engineSchemaText);
  });

  it("has a title (names the generated root type) and the 2020-12 dialect", () => {
    expect((crosscheckReportSchema as { title?: string }).title).toBe("CrosscheckReport");
    expect((crosscheckReportSchema as { $schema?: string }).$schema).toBe(
      "https://json-schema.org/draft/2020-12/schema"
    );
  });

  it("compiles without ajv strict-mode complaints", () => {
    expect(() => compileCrosscheckReport()).not.toThrow();
  });

  it("validates a real report the engine's compare() produced", () => {
    const validate = compileCrosscheckReport();
    const example = loadExample("crosscheck-report.f06.json");
    const valid = validate(example);
    if (!valid) {
      throw new Error(`example should validate but did not: ${JSON.stringify(validate.errors)}`);
    }
    expect(valid).toBe(true);
  });

  it("rejects a status value outside GREEN/AMBER/RED", () => {
    const validate = compileCrosscheckReport();
    const example = loadExample("crosscheck-report.f06.json") as Record<string, unknown>;
    const broken = { ...example, status: "YELLOW" };
    expect(validate(broken)).toBe(false);
  });

  it("rejects a report missing a required field", () => {
    const validate = compileCrosscheckReport();
    const withoutTotals = loadExample("crosscheck-report.f06.json") as Record<string, unknown>;
    delete withoutTotals.totals;
    expect(validate(withoutTotals)).toBe(false);
  });

  it("rejects an unknown top-level property (additionalProperties: false)", () => {
    const validate = compileCrosscheckReport();
    const example = loadExample("crosscheck-report.f06.json") as Record<string, unknown>;
    const withExtra = { ...example, unexpected_field: true };
    expect(validate(withExtra)).toBe(false);
  });
});
