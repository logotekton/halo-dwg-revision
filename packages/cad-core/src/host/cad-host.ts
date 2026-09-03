/**
 * `CadHost` — the viewer facade of `docs/dev/cadhost-proposal.md`.
 *
 * It owns the mlightcad viewer for the whole renderer: one instance mounted on
 * `#viewer-root` (`docs/contracts/wave-3.md` "렌더러 상태"), documents keyed by
 * the engine's `file_id`, and a normalised event surface. Nothing above it ever
 * sees an mlightcad object, and `dispose()` puts every singleton back.
 *
 * The mlightcad half is behind {@link ViewSurface}; this file is ordinary
 * TypeScript over plain records and can be reasoned about (and partly tested)
 * without a browser.
 */

import type { CadDocumentHandle, CadEntity, CadHandle, CadLayer, CadLayout } from '../surface-types';
import { DocumentStateMachine } from './state-machine';
import type { DocumentRecord } from './state-machine';
import { estimateEntityTier, tierChangeWarnings, tierOf } from './tier';
import type {
  CadEditTx,
  CadHostEvent,
  CadHostEventMap,
  CadHostOptions,
  CadHostStatus,
  CadHostWarning,
  CadOpenMode,
  OpenResult,
  OverlayId,
  OverlayJson,
  ViewBox,
  ViewPoint,
} from './types';
import type { ViewOverlayEntity, ViewSurface } from './view-surface';

/** Default overlay colour: ACI 1 (red), the AutoCAD convention for markup. */
const DEFAULT_OVERLAY_COLOR = 1;
const DEFAULT_OVERLAY_LAYER = 'HALO-OVERLAY';
const DEFAULT_OVERLAY_TEXT_HEIGHT_MM = 250;
const DEFAULT_RENDER_TIMEOUT_MS = 60_000;
/** A repaint after a camera change; generous, but never the whole render budget. */
const FRAME_TIMEOUT_MS = 2_000;

type Listener<E extends CadHostEvent> = (payload: CadHostEventMap[E]) => void;

interface OverlayRecord {
  id: OverlayId;
  handles: CadHandle[];
  visible: boolean;
}

/** Everything `open()` needs to know about the bytes it was handed. */
export interface OpenOptions {
  /** `'dxf'` (default) or `'dwg'`; DWG needs the GPL converter registered. */
  format?: 'dxf' | 'dwg';
  mode?: CadOpenMode;
  /**
   * How the first frame is composed. `'extents'` (default) fits the drawing;
   * `'saved'` restores the viewport stored in the file, which is what AutoCAD
   * does in write mode and is rarely what a viewer wants.
   */
  viewMode?: 'extents' | 'saved';
  /** sha256 of the bytes, forwarded to the document handle for evidence refs. */
  fileSha256?: string;
}

export class CadHost {
  private readonly listeners = new Map<CadHostEvent, Set<Listener<CadHostEvent>>>();
  private readonly machine = new DocumentStateMachine();
  private readonly overlays = new Map<OverlayId, OverlayRecord>();
  private readonly unsubscribes: (() => void)[] = [];
  private readonly renderTimeoutMs: number;
  private readonly defaultMode: CadOpenMode;
  private status: CadHostStatus = 'idle';
  private overlaySequence = 0;
  private disposed = false;

  private constructor(
    private readonly surface: ViewSurface,
    options: CadHostOptions
  ) {
    this.renderTimeoutMs = options.renderTimeoutMs ?? DEFAULT_RENDER_TIMEOUT_MS;
    this.defaultMode = options.mode ?? 'write';
    this.wire();
  }

  /**
   * Mounts the viewer into `options.container` and returns the facade.
   *
   * Creating the surface is the only asynchronous part (the worker HEAD probe);
   * everything after it is synchronous, so the renderer can hold the instance
   * in a ref without a second loading state.
   */
  static async create(options: CadHostOptions): Promise<CadHost> {
    const { createViewSurface } = await import('../mlightcad-surface');
    const surface = await createViewSurface({
      container: options.container,
      assetsBaseUrl: options.assetsBaseUrl.replace(/\/+$/, ''),
      checkWorkers: options.checkWorkers ?? true,
      mode: options.mode ?? 'write',
      ...(options.fontChain ? { fontChain: options.fontChain } : {}),
      ...(options.registerDwgConverter
        ? { registerDwgConverter: options.registerDwgConverter }
        : {}),
    });
    return new CadHost(surface, options);
  }

  /** Test seam: build a host over a stub surface. */
  static withSurface(surface: ViewSurface, options: CadHostOptions): CadHost {
    return new CadHost(surface, options);
  }

  // -------------------------------------------------------------------------
  // events
  // -------------------------------------------------------------------------

  on<E extends CadHostEvent>(event: E, callback: Listener<E>): () => void {
    const set = this.listeners.get(event) ?? new Set<Listener<CadHostEvent>>();
    set.add(callback as Listener<CadHostEvent>);
    this.listeners.set(event, set);
    return () => {
      set.delete(callback as Listener<CadHostEvent>);
    };
  }

  private emit<E extends CadHostEvent>(event: E, payload: CadHostEventMap[E]): void {
    for (const listener of this.listeners.get(event) ?? []) {
      (listener as Listener<E>)(payload);
    }
  }

  private setStatus(next: CadHostStatus): void {
    if (this.status === next) return;
    this.status = next;
    this.emit('statusChanged', { status: next });
  }

  private syncStatus(): void {
    this.setStatus(this.machine.status());
  }

  /**
   * Bridges the viewer's events onto the facade's.
   *
   * Document signals are keyed by the *viewer document name*, which this class
   * controls (`<fileId>.dxf`), so the mapping back to a `fileId` needs no
   * mlightcad object identity.
   */
  private wire(): void {
    this.unsubscribes.push(
      this.surface.onDocument((event) => {
        const fileId = fileIdOf(event.name);
        const record = this.machine.signal(fileId, event.kind);
        if (!record) return;
        if (event.kind === 'activated') this.emit('documentActivated', { fileId });
        if (event.kind === 'destroyed') this.emit('documentClosed', { fileId });
        this.syncStatus();
      }),
      this.surface.onSelection((handles) => {
        this.emit('selectionChanged', { handles });
      }),
      this.surface.onUndoStack(() => {
        this.emit('undoStackChanged', {
          canUndo: this.surface.canUndo(),
          canRedo: this.surface.canRedo(),
        });
      }),
      this.surface.onProgress((event) => {
        const fileId = this.machine.active() ?? '';
        this.emit('openProgress', {
          fileId,
          percentage: event.percentage,
          stage: event.stage,
          warnings: [],
        });
      }),
      this.surface.onOpenFailed((message) => {
        const fileId = this.machine.active() ?? '';
        this.machine.fail(fileId, message);
        this.emit('openFailed', { fileId, message });
        this.syncStatus();
      }),
      this.surface.onMissedData(() => {
        const fonts = this.surface.missingFonts();
        if (fonts.length > 0) this.emit('fontMissing', { fonts });
        const xrefs = this.surface.unresolvedXrefs();
        if (xrefs.length > 0) this.emit('xrefUnresolved', xrefs);
      }),
      this.surface.onEntityChanged((handles, kind) => {
        this.emit('entityChanged', { handles, kind });
      })
    );
  }

  // -------------------------------------------------------------------------
  // lifecycle
  // -------------------------------------------------------------------------

  /**
   * Opens working-DXF bytes (or DWG bytes in the converter window) and waits
   * for the first render to settle.
   *
   * Tier estimation runs *before* the parse, from the byte length alone
   * (ADR-0002 개정 §5), and again from the parsed `entity_count`; both feed
   * `warnings` and the `openProgress` event so the shell can warn once, early.
   */
  async open(
    fileId: string,
    name: string,
    bytes: ArrayBuffer,
    options: OpenOptions = {}
  ): Promise<OpenResult> {
    this.assertLive();
    const format = options.format ?? 'dxf';
    const estimate = estimateEntityTier({ byteLength: bytes.byteLength, format });
    const warnings: CadHostWarning[] = [...estimate.warnings];

    this.machine.begin(fileId, name);
    this.syncStatus();
    if (warnings.length > 0) {
      this.emit('openProgress', { fileId, percentage: 0, stage: 'estimate', warnings });
    }

    const started = Date.now();
    let opened: boolean;
    try {
      // The DWG path transfers the buffer into the parser worker and detaches
      // the caller's copy (spike C.7); `ViewSurface.open` copies first.
      opened = await this.surface.open(
        documentNameOf(fileId, format),
        bytes,
        options.mode ?? this.defaultMode
      );
    } catch (error) {
      this.machine.fail(fileId, messageOf(error));
      this.emit('openFailed', { fileId, message: messageOf(error) });
      this.syncStatus();
      throw error;
    }
    if (!opened) {
      const message = 'cad-core: the viewer refused to open the document';
      this.machine.fail(fileId, message);
      this.emit('openFailed', { fileId, message });
      this.syncStatus();
      throw new Error(message);
    }

    this.machine.signal(fileId, 'created');
    this.machine.beginRender(fileId);
    this.machine.setActive(fileId);
    this.syncStatus();

    const renderIdle = await this.surface.waitUntilIdle(this.renderTimeoutMs);
    if ((options.viewMode ?? 'extents') === 'extents') {
      // Framing happens here, after the scene is idle, and nowhere else: the
      // viewer's own `openViewMode: Extents` re-frames on a later 300 ms tick
      // and would overwrite this (`ViewSurface.open` therefore always asks for
      // `Saved`). The second idle wait is what makes `open()` resolve on a
      // *painted* frame — `zoomTo` only marks the view dirty, so a caller that
      // screenshots immediately would still catch the previous camera.
      this.surface.zoomToFit(this.renderTimeoutMs);
      // `zoomTo` only marks the view dirty; the camera reaches the canvas on
      // the next animation frame. Waiting for `renderFrame` is what makes
      // `open()` resolve on a *painted* frame, so a caller that screenshots
      // straight afterwards sees the drawing and not the previous camera.
      await this.surface.nextFrame(FRAME_TIMEOUT_MS);
    }
    if (!renderIdle) {
      warnings.push({ code: 'render-timeout', i18nKey: 'viewer.warning.renderTimeout' });
    }
    const record = this.machine.renderIdle(fileId);
    this.syncStatus();

    const entityCount = this.surface.entityCount();
    warnings.push(...tierChangeWarnings(estimate.tier, entityCount));
    const fonts = this.surface.missingFonts();
    if (fonts.length > 0) {
      warnings.push({
        code: 'fonts-missing',
        i18nKey: 'viewer.warning.fontsMissing',
        params: { fonts: fonts.join(', ') },
      });
      this.emit('fontMissing', { fonts });
    }
    const xrefs = this.surface.unresolvedXrefs();
    if (xrefs.length > 0) {
      warnings.push({
        code: 'xref-unresolved',
        i18nKey: 'viewer.warning.xrefUnresolved',
        params: { count: xrefs.length },
      });
      this.emit('xrefUnresolved', xrefs);
    }

    const result: OpenResult = {
      fileId,
      name,
      entityCount,
      layers: this.surface.layers().length,
      layouts: this.surface.layouts().length,
      tier: tierOf(entityCount),
      warnings,
      durationMs: record?.durationMs ?? Date.now() - started,
      renderIdle,
    };
    this.emit('documentOpened', result);
    this.emit('renderIdle', { fileId, durationMs: result.durationMs });
    return result;
  }

  /** Brings an already open document to the front (MDI, spike C.10). */
  async activate(fileId: string): Promise<void> {
    this.assertLive();
    const record = this.machine.get(fileId);
    if (!record) throw new Error(`cad-core: no open document ${fileId}`);
    const name = documentNameOf(fileId, 'dxf');
    const ok =
      (await this.surface.activate(name)) ||
      (await this.surface.activate(documentNameOf(fileId, 'dwg')));
    if (!ok) throw new Error(`cad-core: could not activate ${fileId}`);
    this.machine.setActive(fileId);
    this.emit('documentActivated', { fileId });
    this.syncStatus();
  }

  async close(fileId: string): Promise<void> {
    this.assertLive();
    this.clearOverlays();
    await this.surface.close(documentNameOf(fileId, 'dxf'));
    this.machine.forget(fileId);
    this.emit('documentClosed', { fileId });
    this.syncStatus();
  }

  /**
   * Releases the viewer and all five mlightcad singletons
   * (`AcApDocManager`, `AcDbDatabaseConverterManager`, `AcApXrefManager`,
   * `FontManager`, `AcTrMTextRenderer`). The heap-growth test of this task
   * exercises exactly this path.
   */
  async dispose(): Promise<void> {
    if (this.disposed) return;
    this.disposed = true;
    for (const unsubscribe of this.unsubscribes.splice(0)) unsubscribe();
    this.listeners.clear();
    this.overlays.clear();
    await this.surface.dispose();
    this.status = 'idle';
  }

  // -------------------------------------------------------------------------
  // read
  // -------------------------------------------------------------------------

  getStatus(): CadHostStatus {
    return this.status;
  }

  documents(): DocumentRecord[] {
    return this.machine.documents();
  }

  activeFileId(): string | null {
    return this.machine.active();
  }

  /**
   * The active document as the same handle `openDxf()` returns, so
   * `statsByLayer`, `exportNdj` and `entityRef` work unchanged on what the user
   * is looking at (ADR-0002 §2: viewer and engine share one key space).
   */
  document(): CadDocumentHandle | null {
    this.assertLive();
    return this.surface.documentHandle();
  }

  getEntityByHandle(handle: CadHandle): CadEntity | undefined {
    const wanted = handle.toUpperCase();
    for (const entity of this.entities()) {
      if (entity.handle.toUpperCase() === wanted) return entity;
    }
    return undefined;
  }

  *entities(options: { space?: 'MODEL' | 'PAPER'; layer?: string } = {}): Iterable<CadEntity> {
    const document = this.surface.documentHandle();
    if (!document) return;
    for (const space of document.spaces()) {
      if (options.space === 'MODEL' && space.space !== 'MODEL') continue;
      if (options.space === 'PAPER' && !space.space.startsWith('PAPER')) continue;
      for (const entity of space.entities()) {
        if (options.layer !== undefined && entity.layer !== options.layer) continue;
        yield entity;
      }
    }
  }

  layers(): CadLayer[] {
    return this.surface.layers();
  }

  layouts(): CadLayout[] {
    return this.surface.layouts();
  }

  activeLayout(): string | null {
    return this.surface.activeLayoutHandle();
  }

  /** Switches the paper space shown, by block-record handle (spike C.8). */
  setActiveLayout(blockRecordHandle: string): boolean {
    this.assertLive();
    return this.surface.setActiveLayout(blockRecordHandle);
  }

  // -------------------------------------------------------------------------
  // view
  // -------------------------------------------------------------------------

  /** Hit test. `worldPoint` is in drawing units, `hitRadiusPx` in pixels (spike C.3). */
  pick(worldPoint: ViewPoint, hitRadiusPx = 8): CadHandle[] {
    return this.surface.pick(worldPoint, hitRadiusPx);
  }

  search(box: ViewBox): CadHandle[] {
    return this.surface.search(box);
  }

  selectByBox(
    box: ViewBox,
    mode: 'window' | 'crossing' = 'crossing',
    action: 'replace' | 'add' | 'remove' = 'replace'
  ): void {
    this.surface.selectByBox(box, mode, action);
  }

  setSelection(handles: CadHandle[]): void {
    this.surface.setSelection(handles);
  }

  selection(): CadHandle[] {
    return this.surface.selection();
  }

  highlight(handles: CadHandle[]): void {
    this.surface.highlight(handles);
  }

  unhighlight(handles: CadHandle[]): void {
    this.surface.unhighlight(handles);
  }

  zoomTo(box: ViewBox, margin?: number): void {
    this.surface.zoomTo(box, margin);
  }

  zoomToFit(): void {
    this.surface.zoomToFit(this.renderTimeoutMs);
  }

  zoomToLayer(layerName: string): boolean {
    return this.surface.zoomToLayer(layerName);
  }

  screenToWorld(point: ViewPoint): ViewPoint {
    return this.surface.screenToWorld(point);
  }

  worldToScreen(point: ViewPoint): ViewPoint {
    return this.surface.worldToScreen(point);
  }

  // -------------------------------------------------------------------------
  // overlays
  // -------------------------------------------------------------------------

  /**
   * Draws a transient overlay and resolves once it is really in the scene.
   *
   * `addTransientEntity()` is fire-and-forget in 1.14.3 (spike C.5), so the
   * surface polls the scene for the objects; without that a caller that adds
   * an overlay and immediately hides it silently loses the call.
   */
  async addOverlay(spec: OverlayJson): Promise<OverlayId> {
    this.assertLive();
    const id = spec.id ?? `overlay-${String((this.overlaySequence += 1))}`;
    const entities = spec.entities.map(toViewOverlayEntity);
    const handles = await this.surface.addTransient(
      entities,
      spec.color ?? DEFAULT_OVERLAY_COLOR,
      spec.layer ?? DEFAULT_OVERLAY_LAYER
    );
    this.overlays.set(id, { id, handles, visible: true });
    return id;
  }

  setOverlayVisible(id: OverlayId, visible: boolean): boolean {
    const record = this.overlays.get(id);
    if (!record) return false;
    const ok = this.surface.setTransientVisible(record.handles, visible);
    if (ok) record.visible = visible;
    return ok;
  }

  removeOverlay(id: OverlayId): void {
    const record = this.overlays.get(id);
    if (!record) return;
    this.surface.removeTransient(record.handles);
    this.overlays.delete(id);
  }

  clearOverlays(): void {
    for (const id of [...this.overlays.keys()]) this.removeOverlay(id);
  }

  overlayIds(): OverlayId[] {
    return [...this.overlays.keys()];
  }

  // -------------------------------------------------------------------------
  // edit
  // -------------------------------------------------------------------------

  /** Runs a viewer command (`docs/spikes/mlightcad-api.md` D.2). */
  async runCommand(name: string, script?: string[]): Promise<void> {
    this.assertLive();
    await this.surface.runCommand(name, script);
  }

  /**
   * One undo mark around `fn` (`acapRunDatabaseEdit`). The transaction exposes
   * only the four operations the spike verified end to end.
   */
  edit<T>(label: string, fn: (tx: CadEditTx) => T): T {
    this.assertLive();
    return this.surface.runEdit(label, (service) => fn(service));
  }

  undo(): boolean {
    const ok = this.surface.undo();
    if (ok) this.emit('undoStackChanged', { canUndo: this.canUndo(), canRedo: this.canRedo() });
    return ok;
  }

  redo(): boolean {
    const ok = this.surface.redo();
    if (ok) this.emit('undoStackChanged', { canUndo: this.canUndo(), canRedo: this.canRedo() });
    return ok;
  }

  canUndo(): boolean {
    return this.surface.canUndo();
  }

  canRedo(): boolean {
    return this.surface.canRedo();
  }

  // -------------------------------------------------------------------------
  // fonts
  // -------------------------------------------------------------------------

  /**
   * Sets the font fallback chain on the main thread **and** the MTEXT worker
   * pool — the two have separate `FontManager` instances and only
   * `AcTrMTextRenderer.setDefaultFonts()` reaches the worker (spike B.3).
   */
  async setFontChain(chain: string[]): Promise<void> {
    this.assertLive();
    await this.surface.setFontChain(chain);
  }

  missingFonts(): string[] {
    return this.surface.missingFonts();
  }

  private assertLive(): void {
    if (this.disposed) throw new Error('cad-core: this CadHost has been disposed');
  }
}

function toViewOverlayEntity(spec: OverlayJson['entities'][number]): ViewOverlayEntity {
  switch (spec.kind) {
    case 'line':
      return { kind: 'line', start: spec.start, end: spec.end };
    case 'polyline':
      return { kind: 'polyline', points: spec.points, closed: spec.closed ?? false };
    case 'rect':
      return {
        kind: 'polyline',
        closed: true,
        points: [
          { x: spec.box.min.x, y: spec.box.min.y },
          { x: spec.box.max.x, y: spec.box.min.y },
          { x: spec.box.max.x, y: spec.box.max.y },
          { x: spec.box.min.x, y: spec.box.max.y },
        ],
      };
    case 'circle':
      return { kind: 'circle', center: spec.center, radiusMm: spec.radiusMm };
    case 'text':
      return {
        kind: 'text',
        position: spec.position,
        text: spec.text,
        heightMm: spec.heightMm ?? DEFAULT_OVERLAY_TEXT_HEIGHT_MM,
      };
  }
}

/**
 * The viewer derives the file type from the document name's extension, so the
 * name is `<fileId>.<ext>` — unique per file and correct for the parser.
 */
function documentNameOf(fileId: string, format: 'dxf' | 'dwg'): string {
  return `${fileId}.${format}`;
}

function fileIdOf(documentName: string): string {
  return documentName.replace(/\.(dxf|dwg)$/i, '');
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
