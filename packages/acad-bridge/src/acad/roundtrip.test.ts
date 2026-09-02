import path from "node:path";
import { rmSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { ACadVersion } from "@node-projects/acad-ts";

import { readDwgFile, readDxfFile } from "./read";
import { writeDwgFile, writeDxfFile } from "./write";
import { buildStats } from "./stats-builder";
import { fixturePath, makeScratchDir } from "./test-paths";
import type { DropEntry } from "../drops";

/**
 * Drops that would mean acad-ts actually lost or miscounted geometry, as
 * opposed to informational reader bookkeeping noise. A DWG-round-tripped
 * document with ATTRIB entities produces two such benign
 * `read-notification`s on the next DXF re-read ("Table reference ...
 * Standard not found for AttributeEntity", "Repeated handle found NNN") --
 * observed empirically to leave the attribute's *value* and every stats
 * measure this package computes unaffected, and entity handles exactly
 * preserved (this test asserts both). `acad-ts-unsupported` and
 * `stats-schema-unsupported-type` drops (drops.ts) are never noise: they
 * mean an entity was actually excluded from, or misclassified in, stats.
 * See README.md "Round-trip results".
 */
function dataAffectingDrops(drops: DropEntry[]): DropEntry[] {
  return drops.filter((d) => d.reason !== "read-notification");
}

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
 * DXF -> DWG -> DXF, then compares acad-ts stats of the reread final DXF
 * against the original DXF's stats (brief W2-05, round-trip test 1).
 *
 * F02 (blocks, nested blocks, rotated/scaled INSERTs with ATTRIB) is used
 * here rather than F06: F06 (and F10_grid) hit a real, isolated acad-ts
 * reader bug -- a BLOCK and a LAYER sharing the same name ("X-TITLE") makes
 * `DxfReader` fail to resolve the INSERT's block reference, which then gets
 * silently dropped on the next DWG write. That gap is covered by its own
 * regression test below rather than folded into the exact-match assertion
 * here. See README.md "Round-trip results".
 */
describe("DXF -> DWG -> DXF round trip (F02)", () => {
  it("acad-ts stats match exactly, and entity handles survive unchanged", () => {
    const src = fixturePath("F02.dxf");
    const dir = scratch("f02-roundtrip");
    const dwgPath = path.join(dir, "F02.dwg");
    const dxfPath = path.join(dir, "F02.rt.dxf");

    const before = readDxfFile(src);
    expect(dataAffectingDrops(before.drops)).toEqual([]);
    const beforeStats = buildStats(before.doc);
    expect(dataAffectingDrops(beforeStats.drops)).toEqual([]);
    const modelSpaceBefore = before.doc.modelSpace;
    if (!modelSpaceBefore) throw new Error("no model space");
    const beforeHandles = [...modelSpaceBefore.entities].map((e) => e.handle);

    if (!before.doc.header) throw new Error("no header");
    before.doc.header.version = ACadVersion.AC1027;
    writeDwgFile(before.doc, dwgPath);

    const dwgRead = readDwgFile(dwgPath);
    if (!dwgRead.doc.header) throw new Error("no header");
    dwgRead.doc.header.version = ACadVersion.AC1032;
    writeDxfFile(dwgRead.doc, dxfPath);

    const after = readDxfFile(dxfPath);
    expect(dataAffectingDrops(after.drops)).toEqual([]);
    const afterStats = buildStats(after.doc);
    expect(dataAffectingDrops(afterStats.drops)).toEqual([]);
    const modelSpaceAfter = after.doc.modelSpace;
    if (!modelSpaceAfter) throw new Error("no model space");
    const afterHandles = [...modelSpaceAfter.entities].map((e) => e.handle);

    expect(afterStats.totals).toEqual(beforeStats.totals);
    expect(afterStats.buckets).toEqual(beforeStats.buckets);
    expect(afterHandles).toEqual(beforeHandles);
  });
});

describe("known gap: BLOCK and LAYER sharing a name (F06, F10_grid)", () => {
  it.each(["F06", "F10_grid"])(
    "%s: the X-TITLE INSERT's block reference is unresolved on read, and dropped on DWG write",
    (fixture) => {
      const src = fixturePath(`${fixture}.dxf`);
      const dir = scratch(`${fixture}-known-gap`);
      const dwgPath = path.join(dir, `${fixture}.dwg`);

      const before = readDxfFile(src);
      const beforeStats = buildStats(before.doc);
      const titleInsertDrop = beforeStats.drops.find(
        (d) => d.message === "INSERT references an unresolved block record"
      );
      expect(titleInsertDrop).toBeDefined();
      expect(titleInsertDrop?.layer).toBe("X-TITLE");

      if (!before.doc.header) throw new Error("no header");
      before.doc.header.version = ACadVersion.AC1027;
      writeDwgFile(before.doc, dwgPath);

      const dwgRead = readDwgFile(dwgPath);
      const afterStats = buildStats(dwgRead.doc);

      // Exactly one INSERT (the unresolved X-TITLE one) is missing after the
      // DWG round trip; every other measure is unaffected.
      expect(afterStats.totals.count_by_type.INSERT).toBe((beforeStats.totals.count_by_type.INSERT ?? 0) - 1);
      expect(afterStats.totals.length_sum_mm).toBe(beforeStats.totals.length_sum_mm);
      expect(afterStats.totals.hatch_area_sum_mm2).toBe(beforeStats.totals.hatch_area_sum_mm2);
    }
  );
});
