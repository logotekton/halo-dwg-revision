/**
 * `@halo-cad/schema` — the JSON Schema contract between the viewer
 * (TypeScript) and the engine (Python), plus the compiled runtime validators.
 *
 * The schemas in `src/` are the single source of truth. `gen/ts` and
 * `gen/python` are generated from them and committed; never edit those by hand.
 */
export * from "./schemas";
export * from "./validate";
export type * from "../gen/ts/index";
