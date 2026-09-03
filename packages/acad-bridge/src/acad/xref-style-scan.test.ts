import { describe, expect, it } from "vitest";
import { readDwgFile } from "./read";
import { fixturePath } from "./test-paths";
import { collectStyles, collectXrefs } from "./xref-style-scan";

/**
 * W3-06: `info --xrefs`'s two extra arrays, read straight off the acad-ts
 * object model. F10_host.dwg (fixtures/gen's XREF fixture pair) has
 * exactly one XREF block (F10_GRID -> F10_grid.dxf) and the default
 * `new_doc()` STYLE table.
 */
describe("collectXrefs", () => {
  it("finds F10_host.dwg's one XREF block and its declared path", () => {
    const { doc } = readDwgFile(fixturePath("F10_host.dwg"));
    const xrefs = collectXrefs(doc);

    expect(xrefs).toEqual([{ block_name: "F10_GRID", path: "F10_grid.dxf" }]);
  });

  it("a document with no XREF blocks returns an empty array", () => {
    const { doc } = readDwgFile(fixturePath("F02.dwg"));
    expect(collectXrefs(doc)).toEqual([]);
  });
});

describe("collectStyles", () => {
  it("lists every STYLE table entry with its font/bigfont/typeface fields", () => {
    const { doc } = readDwgFile(fixturePath("F10_host.dwg"));
    const styles = collectStyles(doc);

    expect(styles.length).toBeGreaterThan(0);
    for (const style of styles) {
      expect(typeof style.name).toBe("string");
      expect(typeof style.font).toBe("string");
      expect(typeof style.bigfont).toBe("string");
      expect(style.typeface === null || typeof style.typeface === "string").toBe(true);
    }
  });
});
