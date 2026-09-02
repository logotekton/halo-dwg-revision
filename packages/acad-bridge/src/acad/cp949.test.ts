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
 * F03 cp949 R2000 DXF -> DWG: text preservation (brief W2-05, round-trip
 * test 3). acad-ts's README claims `$DWGCODEPAGE`-aware decoding for ASCII
 * DXF, but reading fixtures/generated/F03_r2000_cp949.dxf here shows it does
 * NOT: TEXT values come back as Latin-1-shaped mojibake (e.g. "°Å½Ç" instead
 * of "거실"), not valid Hangul. Per the brief's "Defaults for ambiguity" this
 * is recorded rather than worked around (see README.md "Known gaps" and the
 * task report's Questions for gate) -- this package does not implement its
 * own cp949 decoder to paper over it.
 *
 * What this test actually checks, given that: whatever acad-ts decodes the
 * TEXT/MTEXT content to (correct or not) survives a DXF -> DWG -> stats
 * round trip byte-for-byte (`text_hash`/`text_count` unchanged) -- i.e. the
 * corruption happens once, at the initial DXF decode, and is not made worse
 * by this package's own DWG conversion path.
 */
describe("F03 cp949 R2000 DXF -> DWG: text round-trips as decoded", () => {
  it("text_hash and text_count are unchanged after the DWG round trip (decode itself is a known acad-ts gap)", () => {
    const dir = makeScratchDir("cp949");
    scratchDirs.push(dir);
    const dwgPath = path.join(dir, "F03.dwg");

    const src = readDxfFile(fixturePath("F03_r2000_cp949.dxf"));
    expect(src.drops).toEqual([]);
    const before = buildStats(src.doc);
    expect(before.totals.text_count).toBeGreaterThan(0);

    const modelSpace = src.doc.modelSpace;
    if (!modelSpace) throw new Error("no model space");
    const texts = [...modelSpace.entities].filter((e): e is TextEntity => e instanceof TextEntity).map((e) => e.value);
    expect(texts.length).toBeGreaterThan(0);
    // Known gap, not asserted as correct: this is mojibake, not Hangul.
    // `À-ÿ` is the Latin-1 supplement range the cp949 bytes land
    // in when misread as a single-byte Western codepage.
    expect(texts.some((t) => /[À-ÿ]/.test(t))).toBe(true);

    if (!src.doc.header) throw new Error("no header");
    src.doc.header.version = ACadVersion.AC1027;
    writeDwgFile(src.doc, dwgPath);

    const dwgRead = readDwgFile(dwgPath);
    const after = buildStats(dwgRead.doc);

    expect(after.totals.text_count).toBe(before.totals.text_count);
    expect(after.totals.text_hash).toBe(before.totals.text_hash);
  });
});
