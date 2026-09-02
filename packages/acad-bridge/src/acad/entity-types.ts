/**
 * Maps acad-ts's `entity.objectName` (its raw DXF type token, e.g. from
 * `DxfFileToken`) onto `LayerStatsDocument`'s closed `entity_type` enum
 * (packages/schema/src/ndj/entity.schema.json#/$defs/entity_type):
 *
 *   LINE LWPOLYLINE POLYLINE ARC CIRCLE ELLIPSE SPLINE TEXT MTEXT ATTRIB
 *   ATTDEF INSERT HATCH DIMENSION LEADER MLEADER SOLID POINT 3DFACE PROXY
 *
 * Two acad-ts tokens do not match a same-named schema value 1:1:
 *
 * - `MULTILEADER` (acad-ts's `MultiLeader.objectName`, and the real DXF
 *   group-code type name -- see fixtures/README.md Decision 10) has no
 *   `MULTILEADER` entry in the schema enum, only `MLEADER`. This is a
 *   naming split between docs/contracts/stats-definition.md (prose, uses
 *   "MULTILEADER") and the schema (uses "MLEADER") -- see this package's
 *   README "Deviations" and the task report's Questions for gate.
 * - `ARC_DIMENSION` (`DimensionArc.objectName`) is normalised to
 *   `DIMENSION`, per stats-definition.md "DIMENSION 하위 유형은 모두
 *   DIMENSION" -- every other Dimension subclass already reports
 *   `objectName === "DIMENSION"` directly.
 *
 * Anything not listed here (VIEWPORT, XLINE, REGION, MLINE, ...) has no slot
 * in the schema enum at all. `normalizeEntityType` returns `null` for those;
 * the caller excludes the entity from stats and records a
 * `stats-schema-unsupported-type` drop instead of emitting an invalid
 * document (see drops.ts).
 */
const DIRECT: ReadonlySet<string> = new Set([
  "LINE",
  "LWPOLYLINE",
  "POLYLINE",
  "ARC",
  "CIRCLE",
  "ELLIPSE",
  "SPLINE",
  "TEXT",
  "MTEXT",
  "ATTRIB",
  "ATTDEF",
  "INSERT",
  "HATCH",
  "DIMENSION",
  "LEADER",
  "SOLID",
  "POINT",
  "3DFACE",
]);

const RENAMED: ReadonlyMap<string, string> = new Map([
  ["MULTILEADER", "MLEADER"],
  ["ARC_DIMENSION", "DIMENSION"],
  ["ACAD_PROXY_ENTITY", "PROXY"],
]);

/** Normalised type name, or `null` if `objectName` has no schema `entity_type` slot. */
export function normalizeEntityType(objectName: string): string | null {
  if (DIRECT.has(objectName)) return objectName;
  const renamed = RENAMED.get(objectName);
  if (renamed) return renamed;
  return null;
}

/** Normalised types whose `length_sum_mm` contribution is computed by acad/length.ts. */
export const LENGTH_TYPES: ReadonlySet<string> = new Set([
  "LINE",
  "LWPOLYLINE",
  "POLYLINE",
  "ARC",
  "CIRCLE",
  "ELLIPSE",
  "SPLINE",
]);
