import { parseArgs } from "node:util";

import { readDxfFile } from "../acad/read";
import { scanUnsupported } from "../acad/scan-unsupported";
import { DEFAULT_DXF2DWG_VERSION, parseVersionName } from "../acad/version";
import { writeDwgFile } from "../acad/write";
import { buildDropsReport, dropsSidecarPath, type DropEntry } from "../drops";
import { ACAD_TS_VERSION, writeJsonFile } from "../util";

const USAGE = "Usage: acad-bridge dxf2dwg <in.dxf> <out.dwg> [--version AC1027]";

export function runDxf2Dwg(argv: string[]): number {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { version: { type: "string", default: DEFAULT_DXF2DWG_VERSION } },
  });
  const [input, output] = positionals;
  if (!input || !output) {
    process.stderr.write(`${USAGE}\n`);
    return 1;
  }
  const version = parseVersionName(values.version ?? DEFAULT_DXF2DWG_VERSION);

  const { doc, drops: readDrops } = readDxfFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);
  doc.header.version = version;
  writeDwgFile(doc, output);

  const allDrops: DropEntry[] = [...readDrops, ...scanUnsupported(doc)];
  writeJsonFile(dropsSidecarPath(output), buildDropsReport(input, ACAD_TS_VERSION, allDrops));

  process.stdout.write(`wrote ${output} (${allDrops.length.toString()} drops)\n`);
  return 0;
}
