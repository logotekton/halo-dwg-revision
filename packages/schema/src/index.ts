/**
 * `@halo-cad/schema` — the JSON Schema contract between the viewer
 * (TypeScript) and the engine (Python), plus the compiled runtime validators.
 *
 * The schemas in `src/` are the single source of truth. `gen/ts` and
 * `gen/python` are generated from them and committed; never edit those by hand.
 *
 * The `compare/*` family (R1) is exported the same way as the rest:
 * `validateClustersSidecar`, `validateSheetPair`, ... from `./validate`, and
 * the root types (`ClustersSidecar`, `SheetPair`, `Change`, `Cluster`, `Run`,
 * `SheetFrame`, `CompareSetSummary`, `RevisionTruth`) from the generated barrel.
 */
export * from "./schemas";
export * from "./validate";
export type * from "../gen/ts/index";
