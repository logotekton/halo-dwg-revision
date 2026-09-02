import path from "node:path";
import { rmSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { ACadVersion, TextEntity } from "@node-projects/acad-ts";

import { readDwgFile, readDxfFile } from "./read";
import { writeDwgFile } from "./write";
import { buildStats } from "./stats-builder";
import { fixturePath, makeScratchDir } from "./test-paths";

const scratchDirs: string[] = [];
afterEach(() => {
  for (const dir of scratchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/**
 * F03 cp949 R2000 DXF -> DWG -> Korean text preserved (brief W2-05,
 * round-trip test 3). acad-ts follows `$DWGCODEPAGE` when decoding the DXF
 * (README "Reading a DXF file"); this checks that decode survives a DWG
 * write by comparing the aggregate `text_hash` (NFC-normalised TEXT/MTEXT
 * content) before and after, rather than just eyeballing a few characters.
 */
describe("F03 cp949 R2000 DXF -> DWG: Korean text preserved", () => {
  it("text_hash and text_count are unchanged after the DWG round trip", () => {
    const dir = makeScratchDir("cp949");
    scratchDirs.push(dir);
    const dwgPath = path.join(dir, "F03.dwg");

    const src = readDxfFile(fixturePath("F03_r2000_cp949.dxf"));
    expect(src.drops).toEqual([]);
    const before = buildStats(src.doc);
    expect(before.totals.text_count).toBeGreaterThan(0);

    // A sample Korean string is present verbatim, not mojibake -- catches a
    // codepage mixup even if the hash comparison below were somehow vacuous.
    const modelSpace = src.doc.modelSpace;
    if (!modelSpace) throw new Error("no model space");
    const texts = [...modelSpace.entities].filter((e): e is TextEntity => e instanceof TextEntity).map((e) => e.value);
    expect(texts.some((t) => /[가-힣]/.test(t))).toBe(true);

    if (!src.doc.header) throw new Error("no header");
    src.doc.header.version = ACadVersion.AC1027;
    writeDwgFile(src.doc, dwgPath);

    const dwgRead = readDwgFile(dwgPath);
    const after = buildStats(dwgRead.doc);

    expect(after.totals.text_count).toBe(before.totals.text_count);
    expect(after.totals.text_hash).toBe(before.totals.text_hash);
  });
});
