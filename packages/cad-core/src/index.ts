/**
 * `@halo-cad/cad-core` — the viewer-side CAD core.
 *
 * Public surface (W2-02):
 *
 * ```ts
 * const doc = await openDxf(bytes);
 * const stats = statsByLayer(doc, { file_sha256 });   // LayerStatsDocument
 * const ndj   = exportNdj(doc, { file_sha256 });      // NdjDocument
 * dispose(doc);
 * ```
 *
 * Every return type comes from `@halo-cad/schema`; no mlightcad type is part of
 * this API, and `mlightcad-surface.ts` is the only file that imports one.
 * See `packages/cad-core/README.md`.
 */

import type { EntityRef } from '@halo-cad/schema/gen/ts/common/entity-ref';

import { disposeDocument, openDwgDatabase, openDxfDatabase, writeDxfText } from './mlightcad-surface';
import type { CadDocumentHandle, CadEntity, CurveLengthPath } from './surface-types';

export type {
  CadBlock,
  CadDocumentHandle,
  CadEntity,
  CadEntityDetail,
  CadExtents,
  CadHandle,
  CadHeader,
  CadLayer,
  CadLayout,
  CadPolylineVertex,
  CadSpace,
  CadSpaceView,
  CadTraits,
  CurveLengthPath,
  NdjEntityType,
  Vec3,
} from './surface-types';

export { SCHEMA_VERSION, VIEWER_PRODUCER } from './constants';
export { normaliseEntityType, mtextToPlain } from './mlightcad-surface';
export { sha1Hex, textHash, compareByCodePoint } from './sha1';
export { statsByLayer } from './stats';
export type { StatsMeta } from './stats';
export { exportNdj, toNdjsonLines } from './ndj';
export type { NdjMeta } from './ndj';
export {
  FLATTEN_DISTANCE_MM,
  cadFitPointCurve,
  clampedUniformKnots,
  evaluateNurbs,
  fitPointSplineLength,
  flattenNurbs,
  nurbsFromControlPoints,
  nurbsLength,
  scanSplineFitData,
} from './curve-length';
export type { NurbsCurve, Point3, SplineFitData } from './curve-length';
export { postProcessDxfOut } from './dxfout-postprocess';
export type { DxfPostProcessReport, DxfPostProcessResult } from './dxfout-postprocess';

// The view half (W3-02): CadHost mounts the mlightcad viewer into a DOM
// container. Node consumers (vitest, the desktop main process) can keep
// importing everything above without pulling the WebGL surface in — the module
// only touches the DOM once `CadHost.create()` is called.
export { CadHost } from './host';
export type {
  CadHostEvent,
  CadHostEventMap,
  CadHostOptions,
  CadHostStatus,
  EntityTier,
  OpenResult,
  OverlayEntitySpec,
  OverlayId,
  OverlayJson,
  ViewBox,
  ViewPoint,
} from './host';
export { DXF_BYTES_PER_ENTITY, DWG_BYTES_PER_ENTITY, estimateEntityTier, tierOf } from './host';

export interface OpenDxfOptions {
  /**
   * Forces the encoding used to decode strings instead of the one derived from
   * `$DWGCODEPAGE`. mlightcad 1.14.3 decodes internally and offers no override
   * hook, so this value is recorded in the NDJ header
   * (`codepage_effective` + `codepage_override_by_user`) but does not change
   * how bytes are decoded. See the W2-02 report, "Questions for gate".
   */
  encoding?: string;
  /** sha256 of the bytes, carried on the handle for convenience. */
  fileSha256?: string;
}

/**
 * Opens working-DXF bytes and returns an opaque handle.
 *
 * The buffer is copied before it is handed to the parser: the DWG path
 * transfers the input into a worker and leaves the caller's `ArrayBuffer`
 * detached (`docs/spikes/mlightcad-api.md` C.7).
 */
export function openDxf(
  bytes: ArrayBuffer,
  options: OpenDxfOptions = {}
): Promise<CadDocumentHandle> {
  return openDxfDatabase(bytes, options);
}

/**
 * Opens DWG bytes headlessly (no viewer, no canvas).
 *
 * Only usable where `@halo-cad/dwg-io-gpl`'s `registerLibreDwgConverter()` has
 * run and a `Worker` global exists — in practice the hidden converter window of
 * `apps/desktop/src/main/convert` (ADR-0002 개정 §2). The desktop main process
 * cannot call it: the DWG parser is worker-only.
 */
export function openDwg(
  bytes: ArrayBuffer,
  options: { fileSha256?: string } = {}
): Promise<CadDocumentHandle> {
  return openDwgDatabase(bytes, options);
}

/**
 * Serialises an open document to DXF text with the viewer's own DXF writer.
 *
 * The result still has the two defects of ADR-0002 개정 §3; run
 * {@link postProcessDxfOut} on it before handing it to the engine.
 */
export function exportDxf(
  document: CadDocumentHandle,
  options: { version?: string; precision?: number } = {}
): string {
  return writeDxfText(document, options);
}

/**
 * Curve length in millimetres per `docs/contracts/stats-definition.md`.
 *
 * Two routes exist (spike C.2) and both are implemented:
 * `intersect-curves` (default) sums the intersect primitives and works for
 * every curve; `entity-properties` reads the computed `geometry.length` of the
 * property inspector and returns `null` for ARC, CIRCLE and SPLINE, which do
 * not publish it in 1.14.3. `test/curve-length.test.ts` cross-checks the two.
 */
export function curveLength(entity: CadEntity, path?: CurveLengthPath): number | null {
  return entity.curveLength(path);
}

/**
 * `EntityRef` of `common/entity-ref.schema.json`: the unit of evidence.
 *
 * `file` defaults to the sha256 the document was opened with; pass `file`
 * explicitly to use the ULID of the `drawing_file` row instead. Throws when
 * neither is available, because an evidence reference without a file
 * identifier cannot be resolved later (CLAUDE.md rule 6).
 */
export function entityRef(
  entity: CadEntity,
  options: { file?: string; role?: string } = {}
): EntityRef {
  const file = options.file ?? entity.file;
  if (file === undefined) {
    throw new Error(
      'cad-core: entityRef needs a file identifier — open the document with { fileSha256 } or pass { file }'
    );
  }
  return {
    file,
    handle: entity.handle.toUpperCase(),
    path: entity.path.map((handle) => handle.toUpperCase()),
    space: entity.space,
    ...(options.role === undefined ? {} : { role: options.role }),
  };
}

/**
 * Releases the database behind the handle. Statistics and NDJ export both walk
 * the whole entity graph, so a long-lived viewer session must call this when a
 * document tab closes or the heap keeps every entity alive.
 */
export function dispose(document: CadDocumentHandle): void {
  disposeDocument(document);
}
