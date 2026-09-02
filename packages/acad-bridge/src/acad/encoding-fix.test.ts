import path from "node:path";
import { rmSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { ACadVersion } from "@node-projects/acad-ts";

import { readDwgFile, readDxfFile } from "./read";
import { writeDwgFile } from "./write";
import { buildStats } from "./stats-builder";
import { fixturePath, makeScratchDir } from "./test-paths";
import truthF03 from "../../../../fixtures/truth/F03.json";
import truthF06 from "../../../../fixtures/truth/F06.json";

const scratchDirs: string[] = [];
afterEach(() => {
  for (const dir of scratchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/**
 * Regression test for the acad-ts windows-1252-forced-decode workaround
 * (README.md "Known acad-ts gaps" #3, acad/decode-fix.ts): acad-ts decodes
 * DXF/DWG text bytes as windows-1252 regardless of the file's real
 * encoding. `fixDocumentTextEncoding` reverses that using acad-ts's own
 * observed byte<->codepoint behaviour (including its three-way handling of
 * CP1252's 5 undefined high bytes) and re-decodes with the real target
 * encoding (UTF-8 for AC1021+, else `$DWGCODEPAGE`).
 *
 * Success criterion (brief follow-up): `stats` on F03.dxf, its cp949
 * variant, F03.dwg, and F06.dxf all produce the exact `text_hash` recorded
 * in fixtures/truth/*.json (computed independently by ezdxf, W2-03).
 */
describe("acad-ts windows-1252 decode workaround", () => {
  it("F03.dxf (R2018 UTF-8): text_hash matches ezdxf truth exactly", () => {
    const { doc } = readDxfFile(fixturePath("F03.dxf"));
    const stats = buildStats(doc);
    expect(stats.totals.text_hash).toBe(truthF03.totals.text_hash);
    expect(stats.totals.text_count).toBe(truthF03.totals.text_count);
  });

  it("F03_r2000_cp949.dxf (legacy cp949): text_hash matches the same ezdxf truth", () => {
    const { doc } = readDxfFile(fixturePath("F03_r2000_cp949.dxf"));
    const stats = buildStats(doc);
    expect(stats.totals.text_hash).toBe(truthF03.totals.text_hash);
  });

  it("F03 DXF -> DWG -> stats: text_hash survives the round trip", () => {
    const dir = makeScratchDir("encoding-fix-f03");
    scratchDirs.push(dir);
    const dwgPath = path.join(dir, "F03.dwg");

    const { doc } = readDxfFile(fixturePath("F03.dxf"));
    if (!doc.header) throw new Error("no header");
    doc.header.version = ACadVersion.AC1027;
    writeDwgFile(doc, dwgPath);

    const dwgRead = readDwgFile(dwgPath);
    const stats = buildStats(dwgRead.doc);
    expect(stats.totals.text_hash).toBe(truthF03.totals.text_hash);
  });

  it("F06.dxf: text_hash matches truth (title block's Korean ATTRIB value included)", () => {
    const { doc } = readDxfFile(fixturePath("F06.dxf"));
    const stats = buildStats(doc);
    expect(stats.totals.text_hash).toBe(truthF06.totals.text_hash);
  });
});
