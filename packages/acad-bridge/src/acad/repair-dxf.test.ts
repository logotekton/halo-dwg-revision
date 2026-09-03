import { rmSync } from "node:fs";
import path from "node:path";
import { AttributeBase, MText } from "@node-projects/acad-ts";
import { afterEach, describe, expect, it } from "vitest";

import { repairDxfText } from "./repair-dxf";
import { readDwgFile, readDxfFile } from "./read";
import { writeDxfFile } from "./write";
import { walkSpaceEntities } from "./walk";
import { fixturePath, makeScratchDir } from "./test-paths";

const scratchDirs: string[] = [];
function scratch(prefix: string): string {
  const dir = makeScratchDir(prefix);
  scratchDirs.push(dir);
  return dir;
}
afterEach(() => {
  for (const dir of scratchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/**
 * A minimal `CadDocument` stand-in for the two low-level fixes that don't
 * need one (`dedupeDuplicateSeqend`, `normalizeZeroLengthMTextDirection`
 * never touch `doc`): `repairDxfText`'s signature always takes one, so
 * these tests pass an object shaped just enough for `restoreAttributeSubclass`
 * to find nothing and no-op (`doc.blockRecords` absent -> `walkSpaceEntities`
 * yields nothing -> the empty tag map short-circuits that fix).
 */
const NO_ATTRIBUTES_DOC = {} as Parameters<typeof repairDxfText>[1];

describe("dedupeDuplicateSeqend (via repairDxfText)", () => {
  it("removes a byte-identical SEQEND written twice for the same INSERT", () => {
    const text = [
      "  0",
      "INSERT",
      "  5",
      "9E",
      "  0",
      "SEQEND",
      "  5",
      "9F",
      "330",
      "9E",
      "100",
      "AcDbEntity",
      "  8",
      "X-GRID",
      "  0",
      "SEQEND",
      "  5",
      "9F",
      "330",
      "9E",
      "100",
      "AcDbEntity",
      "  8",
      "X-GRID",
      "  0",
      "LINE",
      "  5",
      "A0",
      "",
    ].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.duplicateSeqendRemoved).toBe(1);
    expect(result.remainingDuplicateHandlesReassigned).toBe(0);
    // Exactly one SEQEND record survives.
    expect((result.text.match(/\n {2}0\nSEQEND\n/g) ?? []).length).toBe(1);
    expect(result.text).toContain("LINE");
  });

  it("leaves two SEQENDs for different INSERTs untouched (not adjacent duplicates)", () => {
    const text = [
      "  0",
      "SEQEND",
      "  5",
      "10",
      "330",
      "1",
      "  0",
      "SEQEND",
      "  5",
      "11",
      "330",
      "2",
      "",
    ].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.duplicateSeqendRemoved).toBe(0);
    expect((result.text.match(/(?:^|\n) {2}0\nSEQEND\n/g) ?? []).length).toBe(2);
  });
});

describe("normalizeZeroLengthMTextDirection (via repairDxfText)", () => {
  it("replaces a (0, 0, 0) MTEXT direction vector with (1, 0, 0)", () => {
    const text = [
      "  0",
      "MTEXT",
      "  5",
      "A1",
      "100",
      "AcDbMText",
      " 10",
      "0",
      " 20",
      "0",
      " 30",
      "0",
      "  1",
      "hello",
      " 11",
      "0",
      " 21",
      "0",
      " 31",
      "0",
      "",
    ].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.mtextDirectionNormalized).toBe(1);
    expect(result.text).toContain("\n 11\n1\n 21\n0\n 31\n0\n");
  });

  it("leaves a non-zero MTEXT direction vector untouched", () => {
    const text = [
      "  0",
      "MTEXT",
      "  5",
      "A1",
      "100",
      "AcDbMText",
      " 11",
      "0.7071",
      " 21",
      "0.7071",
      " 31",
      "0",
      "",
    ].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.mtextDirectionNormalized).toBe(0);
    expect(result.text).toContain("0.7071");
  });

  it("does not touch a TEXT entity's unrelated group 11 (alignment point)", () => {
    const text = ["  0", "TEXT", "  5", "A1", " 11", "0", " 21", "0", " 31", "0", ""].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.mtextDirectionNormalized).toBe(0);
  });
});

describe("reassignRemainingDuplicateHandles (via repairDxfText)", () => {
  it("mints a fresh handle for a colliding pair that is not a duplicate SEQEND", () => {
    const text = ["  0", "LINE", "  5", "10", "  0", "CIRCLE", "  5", "10", ""].join("\n");

    const result = repairDxfText(text, NO_ATTRIBUTES_DOC);

    expect(result.remainingDuplicateHandlesReassigned).toBe(1);
    const handles = [...result.text.matchAll(/(?:^|\n) {2}5\n([0-9A-F]+)\n/g)].map((m) => m[1]);
    expect(new Set(handles).size).toBe(2);
    expect(handles[0]).toBe("10");
    expect(handles[1]).not.toBe("10");
  });
});

/**
 * Real acad-ts output (brief W3-08 goal 3 acceptance check): `F06.dwg` has
 * the duplicate-SEQEND + missing-ATTRIB-subclass gaps (README "Known acad-ts
 * gaps" #1 and #2 -- #1, the X-TITLE block/layer name collision, is a
 * separate, still-open gap this repair does not touch, see the assertions
 * below), `F03.dwg` has the zero-length MTEXT direction vector.
 */
describe("writeDxfFile repair, real fixtures", () => {
  it("F06: repairs every X-GRID ATTRIB, leaves the documented X-TITLE gap alone", () => {
    const dir = scratch("f06-repair");
    const { doc } = readDwgFile(fixturePath("F06.dwg"));
    const outPath = path.join(dir, "F06.repaired.dxf");

    const repairResult = writeDxfFile(doc, outPath);

    expect(repairResult.duplicateSeqendRemoved).toBe(7);
    expect(repairResult.attributeSubclassRestored).toBe(7);
    expect(repairResult.mtextDirectionNormalized).toBe(0);
    expect(repairResult.remainingDuplicateHandlesReassigned).toBe(0);

    // No duplicate SEQEND left in the file this package itself wrote.
    const seqendCount = (repairResult.text.match(/(?:^|\n) {2}0\nSEQEND\n/g) ?? []).length;
    expect(seqendCount).toBe(7);
    const attributeSubclassCount = (repairResult.text.match(/\n100\nAcDbAttribute\n/g) ?? [])
      .length;
    expect(attributeSubclassCount).toBe(7);

    // acad-ts's own reader accepts every ATTRIB now (no audit-triggered destruction --
    // this is what actually matters for stats.py: the tag value itself, unlike the
    // subclass structure, is never recovered even from a well-formed file, a separate
    // acad-ts reader gap this fix cannot work around -- see README "Known acad-ts gaps"
    // and repair-dxf.ts's restoreAttributeSubclass docstring).
    const reread = readDxfFile(outPath);
    const values: string[] = [];
    for (const { entity } of walkSpaceEntities(reread.doc)) {
      if (entity instanceof AttributeBase) values.push(entity.value);
    }
    expect(values.sort()).toEqual(["X1", "X2", "X3", "X4", "Y1", "Y2", "Y3"]);
  });

  it("F03: normalizes every MTEXT's zero-length direction vector", () => {
    const dir = scratch("f03-repair");
    const { doc } = readDwgFile(fixturePath("F03.dwg"));
    const outPath = path.join(dir, "F03.repaired.dxf");

    const repairResult = writeDxfFile(doc, outPath);

    expect(repairResult.mtextDirectionNormalized).toBe(10);
    expect(repairResult.duplicateSeqendRemoved).toBe(0);
    expect(repairResult.remainingDuplicateHandlesReassigned).toBe(0);

    // acad-ts's own reader confirms every MTEXT direction is a valid unit vector now
    // (not scoped to just group 11/21/31 == 0 in the raw text: other entity types --
    // e.g. SOLID's own point fields -- legitimately have their own unrelated zero
    // vectors elsewhere in the same file).
    const reread = readDxfFile(outPath);
    const mtextDirections: [number, number, number][] = [];
    for (const { entity } of walkSpaceEntities(reread.doc)) {
      if (entity instanceof MText) {
        const point = entity.alignmentPoint;
        mtextDirections.push([point.x, point.y, point.z]);
      }
    }
    expect(mtextDirections).toHaveLength(10);
    for (const direction of mtextDirections) expect(direction).toEqual([1, 0, 0]);
  });
});
