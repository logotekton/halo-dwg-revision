import { parseArgs } from "node:util";

import { assertValid, SCHEMA_VERSION, validateLayerStats, type LayerStatsDocument } from "@halo-cad/schema";

import { readCadFile } from "../acad/read";
import { buildStats } from "../acad/stats-builder";
import { buildDropsReport, dropsSidecarPath, type DropEntry } from "../drops";
import { ACAD_TS_VERSION, sha256File, writeJsonFile } from "../util";

const USAGE = "Usage: acad-bridge stats <in.dwg|in.dxf> --out <json>";

export function runStats(argv: string[]): number {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { out: { type: "string" } },
  });
  const [input] = positionals;
  if (!input || !values.out) {
    process.stderr.write(`${USAGE}\n`);
    return 1;
  }
  const outPath = values.out;

  const { doc, drops: readDrops } = readCadFile(input);
  const { buckets, totals, drops: statsDrops } = buildStats(doc);

  const document: LayerStatsDocument = {
    schema_version: SCHEMA_VERSION,
    file_sha256: sha256File(input),
    producer: { name: "acad-ts", version: ACAD_TS_VERSION },
    buckets,
    totals,
  };
  assertValid(validateLayerStats, document, `stats(${input})`);

  writeJsonFile(outPath, document);
  const allDrops: DropEntry[] = [...readDrops, ...statsDrops];
  writeJsonFile(dropsSidecarPath(outPath), buildDropsReport(input, ACAD_TS_VERSION, allDrops));

  process.stdout.write(
    `wrote ${outPath} (${String(buckets.length)} buckets, ${String(totals.entity_count)} entities, ${String(allDrops.length)} drops)\n`
  );
  return 0;
}
