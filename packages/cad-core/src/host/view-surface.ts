/**
 * The seam between {@link CadHost} and mlightcad.
 *
 * `CadHost` (and everything above it) talks only to this interface; the single
 * implementation lives in `src/mlightcad-surface.ts`, the one file allowed to
 * import the viewer packages. Keeping the seam this narrow is the mitigation
 * the CadHost proposal asks for: the facade uses a dozen viewer methods, and a
 * viewer upgrade can only break them here.
 *
 * Everything crossing the seam is a string, a number or a plain record.
 */

import type { CadDocumentHandle, CadHandle, CadLayer, CadLayout } from '../surface-types';
import type { CadOpenMode, ViewBox, ViewPoint } from './types';

/** Lifecycle events of `AcApDocManager.events`, flattened. */
export interface ViewDocumentEvent {
  /** The `fileName` the document was opened with. */
  name: string;
  kind: 'toBeOpened' | 'created' | 'activated' | 'toBeDestroyed' | 'destroyed';
}

export interface ViewProgressEvent {
  percentage: number;
  stage: string;
}

export interface ViewSurfaceOptions {
  container: HTMLElement;
  /** Root of the deployed viewer assets, no trailing slash. */
  assetsBaseUrl: string;
  checkWorkers: boolean;
  mode: CadOpenMode;
  fontChain?: string[];
  registerDwgConverter?: (workerBaseUrl: string) => void;
}

/** One transient overlay entity, already reduced to numbers. */
export type ViewOverlayEntity =
  | { kind: 'line'; start: ViewPoint; end: ViewPoint }
  | { kind: 'polyline'; points: ViewPoint[]; closed: boolean }
  | { kind: 'circle'; center: ViewPoint; radiusMm: number }
  | { kind: 'text'; position: ViewPoint; text: string; heightMm: number };

export interface ViewSurface {
  /** `areWorkersReady()`; false when the HEAD probe failed. */
  workersReady(): Promise<boolean>;

  /**
   * Opens a document. Framing is *not* part of this call: the viewer's own
   * post-open fit runs on a delayed tick and would race the facade's, so the
   * surface always opens with the file's saved view and `CadHost` decides what
   * the camera does next.
   */
  open(name: string, bytes: ArrayBuffer, mode: CadOpenMode): Promise<boolean>;
  activate(name: string): Promise<boolean>;
  close(name: string): Promise<boolean>;
  /** Names of the open documents, in tab order. */
  documentNames(): string[];
  activeDocumentName(): string | null;

  /** Wraps the active document's database in the same handle `openDxf` returns. */
  documentHandle(): CadDocumentHandle | null;
  entityCount(): number;
  layers(): CadLayer[];
  layouts(): CadLayout[];
  activeLayoutHandle(): string | null;
  setActiveLayout(blockRecordHandle: string): boolean;

  /**
   * Turns one layer on or off in the layer table of the active document.
   *
   * Returns false when no layer of that name exists, which is the contract
   * screen C relies on to notice a compare DXF that is missing `__CMP_ADDED`
   * or `__CMP_REMOVED`.
   */
  setLayerVisible(name: string, visible: boolean): boolean;
  /**
   * Batch form. Returns the names that were applied, sorted; names absent from
   * the layer table are skipped. All changes land before the next painted
   * frame, so the view repaints once.
   */
  setLayersVisible(entries: Record<string, boolean>): string[];

  /** `waitUntilIdle`: resolves true when the scene settled inside the timeout. */
  waitUntilIdle(timeoutMs: number): Promise<boolean>;
  /**
   * Resolves on the view's next painted frame (`renderFrame`), or false on
   * timeout. `waitUntilIdle` is not a substitute: it reports that no entity
   * conversion is pending, which is already true when a camera change has only
   * marked the view dirty.
   */
  nextFrame(timeoutMs: number): Promise<boolean>;
  regen(): void;

  pick(worldPoint: ViewPoint, hitRadiusPx: number): CadHandle[];
  search(box: ViewBox): CadHandle[];
  selectByBox(box: ViewBox, mode: 'window' | 'crossing', action: 'replace' | 'add' | 'remove'): void;
  setSelection(handles: CadHandle[]): void;
  selection(): CadHandle[];
  highlight(handles: CadHandle[]): void;
  unhighlight(handles: CadHandle[]): void;

  zoomTo(box: ViewBox, margin?: number): void;
  zoomToFit(timeoutMs?: number): void;
  zoomToLayer(layerName: string): boolean;
  screenToWorld(point: ViewPoint): ViewPoint;
  worldToScreen(point: ViewPoint): ViewPoint;

  /**
   * Adds transient entities and resolves once they are actually in the scene.
   *
   * `addTransientEntity()` is fire-and-forget (spike C.5), so the
   * implementation polls `AcTrScene.setTransientEntityVisible()`, which returns
   * whether the object exists.
   */
  addTransient(entities: ViewOverlayEntity[], color: number | string, layer: string): Promise<CadHandle[]>;
  setTransientVisible(handles: CadHandle[], visible: boolean): boolean;
  removeTransient(handles: CadHandle[]): void;

  runCommand(name: string, script?: string[]): Promise<void>;
  /** `acapRunDatabaseEdit` — one undo mark around `fn`. */
  runEdit<T>(label: string, fn: (service: ViewEditService) => T): T;
  undo(): boolean;
  redo(): boolean;
  canUndo(): boolean;
  canRedo(): boolean;

  setFontChain(chain: string[]): Promise<void>;
  missingFonts(): string[];
  unresolvedXrefs(): { name: string; path: string; isOverlay: boolean }[];

  onDocument(callback: (event: ViewDocumentEvent) => void): () => void;
  onSelection(callback: (handles: CadHandle[]) => void): () => void;
  onUndoStack(callback: () => void): () => void;
  onProgress(callback: (event: ViewProgressEvent) => void): () => void;
  onOpenFailed(callback: (message: string) => void): () => void;
  onMissedData(callback: () => void): () => void;
  onEntityChanged(
    callback: (handles: CadHandle[], kind: 'append' | 'modify' | 'erase') => void
  ): () => void;

  /** Tears down all five mlightcad singletons (proposal, "취약점" table). */
  dispose(): Promise<void>;
}

/** The subset of `AcApEntityService` the edit transaction exposes. */
export interface ViewEditService {
  erase(handles: CadHandle[]): number;
  move(handles: CadHandle[], displacement: ViewPoint): number;
  rotate(handles: CadHandle[], basePoint: ViewPoint, angleDeg: number): number;
  copy(handles: CadHandle[], displacement: ViewPoint): CadHandle[];
}
