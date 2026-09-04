import { readCadFile } from "../acad/read";
import { buildStats } from "../acad/stats-builder";
import { versionName } from "../acad/version";
import { collectStyles, collectXrefs } from "../acad/xref-style-scan";

const USAGE = "Usage: acad-bridge info <in.dwg|in.dxf> [--xrefs]";

/**
 * `--xrefs` (W3-06 addendum 2, "XREF 목록은 acad-ts info --xrefs... 또는
 * 원본 DWG에서 별도로 얻어 엔진에 전달한다"): adds `xrefs`/`styles` to the
 * plain `info` output. Additive and opt-in on purpose -- the default `info`
 * shape (used by other tasks/tests already) does not change, and walking
 * every BLOCK/STYLE table entry for these two extra arrays costs nothing a
 * caller that only wants version/entity_count should pay for.
 */
export function runInfo(argv: string[]): number {
  const includeXrefs = argv.includes("--xrefs");
  const [input] = argv.filter((a) => a !== "--xrefs");
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

  const info: Record<string, unknown> = {
    file: input,
    version: versionName(doc.header.version),
    code_page: doc.header.codePage,
    entity_count: totals.entity_count,
    count_by_type: totals.count_by_type,
    spaces: [...spaces].sort(),
  };
  if (includeXrefs) {
    info.xrefs = collectXrefs(doc);
    info.styles = collectStyles(doc);
  }
  process.stdout.write(`${JSON.stringify(info, null, 2)}\n`);
  return 0;
}
