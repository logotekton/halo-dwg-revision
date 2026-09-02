/**
 * `count_by_type` keys are **raw DXF record names** (`entity.objectName` --
 * acad-ts's own `DxfFileToken` values, which match the actual DXF group-code
 * type names, e.g. `MULTILEADER`, not an ACAD UI name or a normalised
 * label), per the schema's own doc comment
 * (packages/schema/src/stats/layer-stats.schema.json#/$defs/count_by_type:
 * "Entity count per raw DXF record name (dxfTypeName, e.g. LINE,
 * MULTILEADER, TRACE) ... Keys are not normalised to the NDJ entity_type
 * enum") and the integration note both parsers converged on
 * (docs/contracts/stats-definition.md "통합에서 확정된 사항").
 *
 * This is a change from `packages/schema/src/ndj/entity.schema.json`'s
 * closed `entity_type` enum, which is a *different* constraint used only by
 * NDJ documents and still has `MLEADER` (not `MULTILEADER`) -- irrelevant
 * here. `count_by_type`'s own key constraint is just a shape pattern:
 * `^[A-Z][A-Z0-9_]*$`.
 *
 * One semantic normalisation from stats-definition.md survives regardless
 * of key naming: "DIMENSION 하위 유형은 모두 DIMENSION". Every Dimension
 * subclass reports `objectName === "DIMENSION"` directly except
 * `DimensionArc`, which reports the DXF subclass token `ARC_DIMENSION` --
 * mapped back to `DIMENSION` here.
 */
const KEY_PATTERN = /^[A-Z][A-Z0-9_]*$/;

const SEMANTIC_RENAME: ReadonlyMap<string, string> = new Map([["ARC_DIMENSION", "DIMENSION"]]);

/**
 * `count_by_type` key for `objectName`, or `null` if it does not fit the
 * schema's key pattern at all (observed case: `3DFACE`/`3DSOLID` start with
 * a digit, which `^[A-Z]...` never matches -- none of fixtures/generated
 * use either type, so this is a defensive fallback, not a known-affected
 * path). The caller excludes such an entity from stats and records a
 * `stats-schema-unsupported-type` drop instead of emitting an invalid
 * document (see drops.ts).
 */
export function statsTypeKey(objectName: string): string | null {
  const key = SEMANTIC_RENAME.get(objectName) ?? objectName;
  return KEY_PATTERN.test(key) ? key : null;
}

/** Raw DXF types whose `length_sum_mm` contribution is computed by acad/length.ts. */
export const LENGTH_TYPES: ReadonlySet<string> = new Set([
  "LINE",
  "LWPOLYLINE",
  "POLYLINE",
  "ARC",
  "CIRCLE",
  "ELLIPSE",
  "SPLINE",
]);
