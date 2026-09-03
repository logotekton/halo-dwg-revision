import { BlockTypeFlags, DxfCode, type CadDocument } from "@node-projects/acad-ts";

/**
 * `info --xrefs`'s two extra arrays (`packages/acad-bridge/src/commands/info.ts`,
 * W3-06 addendum 2 / `docs/contracts/wave-3.md` "계약 갱신").
 *
 * Read straight off the acad-ts object model rather than by re-scanning
 * group codes (`tools/bench/scan-dxf.mjs`'s approach) -- `readCadFile`
 * already parsed the DWG/DXF once for `info`'s own stats, so there is no
 * second file read here, just two more table walks over the same
 * `CadDocument`.
 */

export interface XrefEntry {
  block_name: string;
  path: string;
}

export interface StyleEntry {
  name: string;
  font: string;
  bigfont: string;
  typeface: string | null;
}

/**
 * Every XREF BLOCK definition's declared path, verbatim (Windows
 * backslashes and all -- `docs/contracts/wave-3.md`: "XREF 경로는 윈도
 * 상대경로가 표준이며 엔진이 슬래시·NFC 정규화한다", not this CLI).
 */
export function collectXrefs(doc: CadDocument): XrefEntry[] {
  const out: XrefEntry[] = [];
  const blockRecords = doc.blockRecords;
  if (!blockRecords) return out;
  for (const record of blockRecords) {
    const block = record.blockEntity;
    if (!(block.flags & BlockTypeFlags.XRef)) continue;
    out.push({ block_name: record.name, path: block.xRefPath ?? "" });
  }
  return out.sort((a, b) => a.block_name.localeCompare(b.block_name));
}

/**
 * `ACAD` XDATA group 1000 (`ExtendedDataAsciiString`) on a TEXT STYLE table
 * entry carries AutoCAD's resolved TrueType typeface name -- the value the
 * STYLE's own `filename`/`bigFontFilename` (DXF groups 3/4) do not have
 * when the style references a system font by name instead of a file (W3-09
 * 실측 §3.1: acad-ts preserves this; `dxfOut()` drops it entirely, which is
 * exactly why W3-05's font mapping needs this command's output as its
 * input for a `dxfOut()`-converted host).
 */
function findTypeface(style: { extendedData: Iterable<[{ name?: string }, { records: unknown[] }]> }): string | null {
  for (const [appId, data] of style.extendedData) {
    if (appId.name !== "ACAD") continue;
    for (const record of data.records as { code: DxfCode; rawValue: unknown }[]) {
      if (record.code === DxfCode.ExtendedDataAsciiString) {
        return String(record.rawValue);
      }
    }
  }
  return null;
}

export function collectStyles(doc: CadDocument): StyleEntry[] {
  const out: StyleEntry[] = [];
  const textStyles = doc.textStyles;
  if (!textStyles) return out;
  for (const style of textStyles) {
    out.push({
      name: style.name,
      font: style.filename,
      bigfont: style.bigFontFilename ?? "",
      typeface: findTypeface(style),
    });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}
