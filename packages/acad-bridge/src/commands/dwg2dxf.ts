import { parseArgs } from "node:util";

import { readDwgFile } from "../acad/read";
import { scanUnsupported } from "../acad/scan-unsupported";
import { DEFAULT_DWG2DXF_VERSION, parseVersionName } from "../acad/version";
import { writeDxfFile } from "../acad/write";
import { buildDropsReport, dropsSidecarPath, type DropEntry } from "../drops";
import { ACAD_TS_VERSION, writeJsonFile } from "../util";

const USAGE = "Usage: acad-bridge dwg2dxf <in.dwg> <out.dxf> [--version AC1032]";

export function runDwg2Dxf(argv: string[]): number {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { version: { type: "string", default: DEFAULT_DWG2DXF_VERSION } },
  });
  const [input, output] = positionals;
  if (!input || !output) {
    process.stderr.write(`${USAGE}\n`);
    return 1;
  }
  const version = parseVersionName(values.version ?? DEFAULT_DWG2DXF_VERSION);

  const { doc, drops: readDrops } = readDwgFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);
  doc.header.version = version;
  writeDxfFile(doc, output);

  const allDrops: DropEntry[] = [...readDrops, ...scanUnsupported(doc)];
  writeJsonFile(dropsSidecarPath(output), buildDropsReport(input, ACAD_TS_VERSION, allDrops));

  process.stdout.write(`wrote ${output} (${allDrops.length.toString()} drops)\n`);
  return 0;
}
