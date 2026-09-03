import type { CadDocument } from "@node-projects/acad-ts";

import { readCadFile } from "../acad/read";
import { buildStats } from "../acad/stats-builder";
import { versionName } from "../acad/version";

const USAGE = "Usage: acad-bridge info <in.dwg|in.dxf>";

/** One external reference: the block record that carries it and its stored path. */
export interface XrefInfo {
  block_name: string;
  path: string;
  is_overlay: boolean;
}

/** One text style, including the TrueType typeface that only lives in XDATA. */
export interface StyleInfo {
  name: string;
  /** DXF group 3 — the SHX/TTF file name. */
  font: string;
  /** DXF group 4 — the big font file, empty when the style has none. */
  bigfont: string;
  /** `ACAD` XDATA string, e.g. `Dotum`. Present only for TrueType styles. */
  typeface?: string;
}

/**
 * XREF paths as the DWG stores them.
 *
 * `AcDbDatabase.dxfOut()` drops them (W3-09 measured 0 of 133 preserved on the
 * real set), so the converter reads them here instead and passes them on with
 * the conversion result for the engine to re-attach (`docs/contracts/wave-3.md`,
 * `POST /files/{id}/converted`).
 */
export function readXrefs(doc: CadDocument): XrefInfo[] {
  const out: XrefInfo[] = [];
  for (const record of doc.blockRecords ?? []) {
    const path = record.blockEntity.xRefPath;
    if (path === null || path === "") continue;
    // BlockTypeFlags.XRefOverlay === 8; an overlay is not re-attached
    // transitively when the host is itself referenced.
    out.push({ block_name: record.name, path, is_overlay: (record.blockFlags & 8) !== 0 });
  }
  out.sort((a, b) => a.block_name.localeCompare(b.block_name));
  return out;
}

/**
 * Text styles with their TrueType typeface.
 *
 * The typeface is not a DXF group of the STYLE record: it is the first string
 * of the `ACAD` extended-data list (measured: style `돋움` -> `Dotum`). It is
 * the only place a Korean TTF name survives, and `dxfOut()` writes none of it
 * (W3-09: 0 of 838 styles preserved), so the font panel (W3-05) would have
 * nothing to map without this.
 */
export function readStyles(doc: CadDocument): StyleInfo[] {
  const out: StyleInfo[] = [];
  for (const style of doc.textStyles ?? []) {
    const info: StyleInfo = {
      name: style.name,
      font: style.filename,
      bigfont: style.bigFontFilename ?? "",
    };
    const typeface = firstExtendedString(style);
    if (typeface !== undefined) info.typeface = typeface;
    out.push(info);
  }
  out.sort((a, b) => a.name.localeCompare(b.name));
  return out;
}

function firstExtendedString(style: { extendedData?: unknown }): string | undefined {
  const dictionary = style.extendedData as Iterable<[unknown, { records?: unknown }]> | undefined;
  if (!dictionary) return undefined;
  try {
    for (const [, data] of dictionary) {
      const records = (data as { records?: { value?: unknown }[] }).records ?? [];
      for (const record of records) {
        if (typeof record.value === "string" && record.value.length > 0) return record.value;
      }
    }
  } catch {
    // A style without readable XDATA is normal; the caller treats it as "no typeface".
  }
  return undefined;
}

export function runInfo(argv: string[]): number {
  const [input] = argv;
  if (!input) {
    process.stderr.write(`${USAGE}\n`);
    return 1;
  }

  const { doc } = readCadFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);

  const { totals } = buildStats(doc);
  const spaces = new Set<string>();
  // Cheap re-derivation instead of threading space info out of buildStats:
  // totals alone do not carry which spaces existed, but info only needs the
  // count of non-empty ones and modelSpace/paperSpace layouts are cheap to
  // check directly.
  if (doc.modelSpace && doc.modelSpace.entities.count > 0) spaces.add("MODEL");
  if (doc.layouts) {
    for (const layout of doc.layouts) {
      if (layout.name === "Model") continue;
      if ((layout.associatedBlock?.entities.count ?? 0) > 0) spaces.add(`PAPER:${layout.name}`);
    }
  }

  const info = {
    file: input,
    version: versionName(doc.header.version),
    code_page: doc.header.codePage,
    entity_count: totals.entity_count,
    count_by_type: totals.count_by_type,
    spaces: [...spaces].sort(),
    // Both survive the DWG read but not `dxfOut()`, so the DWG converter
    // (apps/desktop/src/main/convert) reads them from here and hands them to
    // the engine with the converted file (W3-09).
    xrefs: readXrefs(doc),
    styles: readStyles(doc),
  };
  process.stdout.write(`${JSON.stringify(info, null, 2)}\n`);
  return 0;
}
