/**
 * The view half of `@halo-cad/cad-core` (W3-02).
 *
 * `CadHost` is the only thing the renderer touches; the mlightcad viewer lives
 * behind {@link ViewSurface} in `src/mlightcad-surface.ts`.
 */

export { CadHost } from './cad-host';
export type { OpenOptions } from './cad-host';
export { DocumentStateMachine } from './state-machine';
export type { DocumentRecord, DocumentSignal, DocumentState } from './state-machine';
export {
  DWG_BYTES_PER_ENTITY,
  DXF_BYTES_PER_ENTITY,
  TIER_A_MAX_ENTITIES,
  TIER_B_MAX_ENTITIES,
  estimateEntityTier,
  tierChangeWarnings,
  tierOf,
  warningsForTier,
} from './tier';
export type { TierEstimate } from './tier';
export { renders, toViewBox } from './types';
export type {
  BoxLike,
  CadEditTx,
  CadHostEvent,
  CadHostEventMap,
  CadHostOptions,
  CadHostStatus,
  CadHostWarning,
  CadOpenMode,
  EntityTier,
  FlatBox,
  LayerDto,
  OpenProgress,
  OpenResult,
  OverlayEntitySpec,
  OverlayId,
  OverlayJson,
  ViewBox,
  ViewPoint,
} from './types';
export type {
  ViewDocumentEvent,
  ViewEditService,
  ViewOverlayEntity,
  ViewProgressEvent,
  ViewSurface,
  ViewSurfaceOptions,
} from './view-surface';
