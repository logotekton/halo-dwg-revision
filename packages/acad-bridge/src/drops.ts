/**
 * Drop report: entities/objects a conversion or stats run could not fully
 * account for. Written as `<out>.drops.json` next to every `stats`,
 * `dwg2dxf`, and `dxf2dwg` output (brief W2-05, ADR-0002 converter
 * evaluation). Two independent reasons land here, and are kept distinguished
 * because they mean different things:
 *
 * - `acad-ts-unsupported`: acad-ts itself could not resolve the entity to a
 *   real class (`UnknownEntity`), could only keep it as proxy graphics
 *   (`ProxyEntity`), could not resolve an INSERT's block reference, or
 *   raised a `NotSupported`/`Warning`/`Error` notification while reading.
 *   This is evidence for ADR-0002's converter choice.
 * - `stats-schema-unsupported-type`: acad-ts read the entity fine, but its
 *   normalised DXF type has no slot in `LayerStatsDocument`'s closed
 *   `entity_type` enum (packages/schema/src/ndj/entity.schema.json). The
 *   entity is excluded from `stats` output so the document still validates;
 *   this is a schema/contract gap, not an acad-ts capability gap.
 */
export interface DropEntry {
  reason: "acad-ts-unsupported" | "stats-schema-unsupported-type" | "read-notification";
  message: string;
  /** DXF type name as acad-ts reports it (`entity.objectName`), when known. */
  entityType?: string;
  /** Uppercase hex handle, when the entity has one. */
  handle?: string;
  space?: string;
  layer?: string;
}

export interface DropsReport {
  source: string;
  producer: "acad-ts";
  producer_version: string;
  drops: DropEntry[];
}

export function buildDropsReport(source: string, producerVersion: string, drops: DropEntry[]): DropsReport {
  return {
    source,
    producer: "acad-ts",
    producer_version: producerVersion,
    drops,
  };
}

/** `/tmp/f06.acad.json` -> `/tmp/f06.acad.drops.json`; `/tmp/F06.rt.dxf` -> `/tmp/F06.rt.drops.json`. */
export function dropsSidecarPath(outPath: string): string {
  const lastDot = outPath.lastIndexOf(".");
  const lastSlash = Math.max(outPath.lastIndexOf("/"), outPath.lastIndexOf("\\"));
  const base = lastDot > lastSlash ? outPath.slice(0, lastDot) : outPath;
  return `${base}.drops.json`;
}
