/**
 * Values written into every document this package emits.
 *
 * `SCHEMA_VERSION` is duplicated from `@halo-cad/schema` on purpose: cad-core
 * imports that package with `import type` only, so nothing from it survives
 * into `dist/` and `require('dist/index.js')` works with no runtime dependency
 * on the schema package. `test/schema-version.test.ts` pins the two together.
 */

/** Contract version of `packages/schema` (`SCHEMA_VERSION` there). */
export const SCHEMA_VERSION = '0.1';

/**
 * `producer` of `ndj/document.schema.json`. The version is the pinned mlightcad
 * data-model release this package is built against (CLAUDE.md stack pins), not
 * the version of cad-core: the crosscheck needs to know which parser produced
 * the numbers.
 */
export const VIEWER_PRODUCER = {
  name: 'viewer.mlightcad',
  version: '1.14.3',
} as const;
