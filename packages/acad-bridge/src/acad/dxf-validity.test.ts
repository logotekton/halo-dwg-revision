import path from "node:path";
import { readFileSync, rmSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";

import { readDwgFile, readDxfFile } from "./read";
import { writeDwgFile, writeDxfFile } from "./write";
import { fixturePath, makeScratchDir } from "./test-paths";
import { ACadVersion } from "@node-projects/acad-ts";

const scratchDirs: string[] = [];
afterEach(() => {
  for (const dir of scratchDirs.splice(0)) rmSync(dir, { recursive: true, force: true });
});

/**
 * `dwg2dxf` output validity (brief W2-05, round-trip test 2): header and
 * section structure checked directly against the ASCII DXF group-code
 * grammar, plus a full acad-ts re-read as the stronger check that the file
 * is not merely well-formed but actually loadable.
 */
describe("dwg2dxf output is a structurally valid DXF", () => {
  it("F06: has HEADER/TABLES/BLOCKS/ENTITIES sections in order, EOF at the end, and acad-ts can re-read it", () => {
    const dir = makeScratchDir("dxf-validity");
    scratchDirs.push(dir);
    const dwgPath = path.join(dir, "F06.dwg");
    const dxfPath = path.join(dir, "F06.rt.dxf");

    const dxfRead = readDxfFile(fixturePath("F06.dxf"));
    if (!dxfRead.doc.header) throw new Error("no header");
    dxfRead.doc.header.version = ACadVersion.AC1027;
    writeDwgFile(dxfRead.doc, dwgPath);

    const dwgRead = readDwgFile(dwgPath);
    if (!dwgRead.doc.header) throw new Error("no header");
    dwgRead.doc.header.version = ACadVersion.AC1032;
    writeDxfFile(dwgRead.doc, dxfPath);

    const text = readFileSync(dxfPath, "utf8");
    const lines = text.split(/\r\n|\n/);
    const trimmed = lines.map((l) => l.trim());

    function sectionIndex(name: string): number {
      for (let i = 0; i < trimmed.length - 3; i++) {
        if (trimmed[i] === "0" && trimmed[i + 1] === "SECTION" && trimmed[i + 2] === "2" && trimmed[i + 3] === name) {
          return i;
        }
      }
      return -1;
    }

    const header = sectionIndex("HEADER");
    const tables = sectionIndex("TABLES");
    const blocks = sectionIndex("BLOCKS");
    const entities = sectionIndex("ENTITIES");
    expect(header).toBeGreaterThanOrEqual(0);
    expect(tables).toBeGreaterThan(header);
    expect(blocks).toBeGreaterThan(tables);
    expect(entities).toBeGreaterThan(blocks);

    // Last two non-empty group-code lines are "0" / "EOF".
    const nonEmpty = trimmed.filter((l) => l.length > 0);
    expect(nonEmpty.at(-2)).toBe("0");
    expect(nonEmpty.at(-1)).toBe("EOF");

    // Every "0"/"SECTION" is matched by a later "0"/"ENDSEC" before the next
    // "0"/"SECTION" (or EOF) -- a cheap structural balance check beyond just
    // locating the four sections above.
    let sectionDepth = 0;
    for (let i = 0; i < trimmed.length - 1; i++) {
      if (trimmed[i] !== "0") continue;
      if (trimmed[i + 1] === "SECTION") sectionDepth++;
      if (trimmed[i + 1] === "ENDSEC") sectionDepth--;
    }
    expect(sectionDepth).toBe(0);

    // Strongest check: acad-ts itself can re-read the file we just validated
    // structurally, and gets the same entity count back.
    const reread = readDxfFile(dxfPath);
    expect(reread.doc.modelSpace?.entities.count).toBe(dwgRead.doc.modelSpace?.entities.count);
  });
});
