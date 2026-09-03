import { writeFileSync } from "node:fs";

import { DwgWriter, DxfWriter, type CadDocument, type DxfWriteTarget } from "@node-projects/acad-ts";

import { repairDxfText, type DxfRepairResult } from "./repair-dxf";

/** `DwgWriter.writeToBuffer` auto-sizes; nothing to grow or retry here. */
export function writeDwgFile(doc: CadDocument, outPath: string): void {
  const bytes = DwgWriter.writeToBuffer(doc);
  writeFileSync(outPath, bytes);
}

/**
 * DXF writing has no auto-sized buffer helper (unlike DWG's
 * `writeToBuffer`), only a fixed-size `Uint8Array` target or a text sink
 * object (`{ write(value: string): void }`). This package always writes DXF
 * through the text sink, appending chunks to an array and joining once at
 * the end -- unbounded size, and simpler than pre-sizing and retrying a
 * `Uint8Array`.
 *
 * Known limitation: the text-sink path yields real JS Unicode strings, not
 * the `\U+XXXX`-escaped legacy-codepage bytes a pre-UTF8-era DXF version
 * (AC1018 and earlier) is supposed to have -- see acad/version.ts
 * `isUtf8EraVersion` and this package's README "Deviations". `dwg2dxf`'s
 * default and every conversion this task performs target AC1032 (R2018,
 * UTF-8 era), where this is exactly correct.
 *
 * Every write is repaired (`repair-dxf.ts`) before it reaches disk: three
 * real acad-ts writer defects (a duplicate SEQEND, ATTRIB missing its
 * `AcDbAttribute` subclass, a zero-length MTEXT direction vector -- see that
 * module's docstring) otherwise make the file unreadable, or silently wrong,
 * for another DXF parser (ezdxf) even though acad-ts's own reader tolerates
 * its own output. The return value carries the repair counts so a caller
 * (the CLI's `.drops.json` sidecar) can report what was fixed.
 */
export function writeDxfFile(
  doc: CadDocument,
  outPath: string,
  binary = false
): DxfRepairResult {
  const chunks: string[] = [];
  const sink: DxfWriteTarget = {
    write(value: string) {
      chunks.push(value);
    },
  };
  DxfWriter.writeToStream(sink, doc, binary);
  const repaired = repairDxfText(chunks.join(""), doc);
  writeFileSync(outPath, repaired.text, "utf8");
  return repaired;
}
