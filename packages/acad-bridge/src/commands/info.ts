import { readCadFile } from "../acad/read";
import { buildStats } from "../acad/stats-builder";
import { versionName } from "../acad/version";

const USAGE = "Usage: acad-bridge info <in.dwg|in.dxf>";

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
  };
  process.stdout.write(`${JSON.stringify(info, null, 2)}\n`);
  return 0;
}
