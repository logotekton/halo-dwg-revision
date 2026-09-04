/**
 * Standalone viewer harness (`halocad://app/viewer.html`).
 *
 * `apps/web/src/app/**` belongs to W3-01, whose shell will host
 * {@link ViewerPanel} in the real layout; until then this page mounts the panel
 * on its own so `pnpm dev` and `tests/e2e/viewer.spec.ts` can exercise the
 * viewer end to end without touching another task's files. It stays useful
 * afterwards as the isolated page for viewer debugging.
 *
 * The `window.__haloViewerTest` hook it installs mirrors the contract's
 * `window.__haloTest` (`docs/contracts/wave-3.md` "테스트 훅") but under its own
 * name, because W3-01 owns `apps/web/src/test-hooks.ts`.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '../../i18n/i18n';
import '../../styles/index.css';
import { ViewerPanel } from './ViewerPanel';
import {
  closeDrawing,
  currentHost,
  disposeCadHost,
  layers,
  onSelection,
  openDrawing,
  setLayersVisible,
  whenRenderIdle,
} from './host';
import { selection, viewer } from './viewer-store';

interface ConvertResult {
  dxf_path: string;
  entity_count: number;
  converter: string;
  warnings: string[];
  /** Read out of the DWG by acad-bridge, because `dxfOut()` loses them (W3-09). */
  xrefs: { block_name: string; path: string }[];
  styles: { name: string; font: string; bigfont: string; typeface?: string | null }[];
}

interface ViewerTestBridge {
  pickFiles(): Promise<string[]>;
  readFile(path: string): Promise<Uint8Array>;
  convertDwg(job: { dwgPath: string; outPath: string }): Promise<ConvertResult>;
  tmpPath(name: string): Promise<string>;
}

interface ViewerTestHooks {
  getStatus(): string;
  getDocuments(): { fileId: string; name: string; layers: number; entities: number }[];
  getSelection(): string[];
  /** Absolute paths from `HALO_E2E_PICK_FILES`. */
  pickFiles(): Promise<string[]>;
  /** Opens one of those paths; DWG goes through the hidden converter window. */
  openFile(path: string): Promise<OpenedDrawing>;
  pick(x: number, y: number, radius?: number): string[];
  setSelection(handles: string[]): void;
  highlight(handles: string[]): void;
  zoomToFit(): void;
  /** Every layer in the layer table. */
  layers(): string[];
  /** The same table with the flags screen C reads (R1-00a). */
  layerStates(): { name: string; visible: boolean; frozen: boolean }[];
  /** Turns one layer on or off; false when the drawing has no such layer. */
  setLayerVisible(name: string, visible: boolean): boolean;
  /** Applies a whole view mode at once (compare-dxf §9). */
  setLayersVisible(entries: Record<string, boolean>): void;
  /** Resolves once the scene settled and a frame was painted. */
  whenRenderIdle(): Promise<void>;
  /** Layers that actually carry a top-level entity, sorted. */
  populatedLayers(): string[];
  close(fileId: string): Promise<void>;
  dispose(): Promise<void>;
  heapUsedBytes(): number | null;
  /** How many documents the host still tracks. */
  viewerDocumentCount(): number;
  /**
   * Render load: top-level entities plus everything inside block definitions.
   * W3-09 found this, not the top-level count, predicts the headless viewer's
   * crashes, so the e2e reports it for the large real drawings.
   */
  renderLoad(): { topLevel: number; inBlocks: number; total: number };
  /**
   * Handle sets delivered to a subscriber taken through `onSelection` *before*
   * any document existed — the order screen C mounts in.
   */
  selectionEvents(): string[][];
  /** Forces a collection when the app was started with `--expose-gc`. */
  collectGarbage(): Promise<boolean>;
}

declare global {
  interface Window {
    __haloViewerTest?: ViewerTestBridge;
    /**
     * Named `__haloViewer`, not `__haloTest`: W3-01 owns
     * `apps/web/src/test-hooks.ts`, which declares `__haloTest` with the
     * shell's own shape. Two `declare global` blocks for one name would not
     * merge.
     */
    __haloViewer?: ViewerTestHooks;
  }
}

function baseName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}

function toArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  return bytes.slice().buffer;
}

/** Length of a lazy iterable; `entities()` is a generator, so it must be walked. */
function count(items: Iterable<unknown>): number {
  let total = 0;
  const iterator = items[Symbol.iterator]();
  while (!iterator.next().done) total += 1;
  return total;
}

/** What the e2e sees for one opened fixture. */
interface OpenedDrawing {
  fileId: string;
  converter: string;
  entityCount: number;
  /** Counts only: the e2e checks that the metadata round trip happened at all. */
  xrefs: number;
  styles: number;
  warnings: string[];
}

async function openPath(path: string): Promise<OpenedDrawing> {
  const bridge = window.__haloViewerTest;
  if (!bridge) throw new Error('__haloViewerTest bridge is missing (HALO_E2E=1 required)');
  const name = baseName(path);
  const fileId = name.replace(/[^A-Za-z0-9_-]/g, '_');

  if (/\.dwg$/i.test(path)) {
    // The viewer never parses DWG itself: main converts it in the hidden
    // window and the renderer opens the working DXF (ADR-0002 §2).
    const outPath = await bridge.tmpPath(`${fileId}.dxf`);
    const result = await bridge.convertDwg({ dwgPath: path, outPath });
    const bytes = await bridge.readFile(result.dxf_path);
    const opened = await openDrawing(fileId, name, toArrayBuffer(bytes));
    return {
      fileId,
      converter: result.converter,
      entityCount: opened.entityCount,
      xrefs: result.xrefs.length,
      styles: result.styles.length,
      warnings: result.warnings,
    };
  }

  const bytes = await bridge.readFile(path);
  const opened = await openDrawing(fileId, name, toArrayBuffer(bytes));
  return {
    fileId,
    converter: 'none',
    entityCount: opened.entityCount,
    xrefs: 0,
    styles: 0,
    warnings: [],
  };
}

function installTestHooks(): void {
  // Subscribed here, at module start-up, with no CadHost yet: screen C's review
  // panel does the same (it mounts before the compare DXF is fetched), so the
  // e2e proves a subscription taken that early still receives events.
  const selectionEvents: string[][] = [];
  onSelection((handles) => {
    selectionEvents.push(handles);
  });

  const hooks: ViewerTestHooks = {
    getStatus: () => viewer.getState().status,
    getDocuments: () =>
      viewer.getState().documents.map((document) => ({
        fileId: document.fileId,
        name: document.name,
        layers: document.layers,
        entities: document.entityCount,
      })),
    getSelection: () => selection.getState().handles,
    pickFiles: async () => (await window.__haloViewerTest?.pickFiles()) ?? [],
    openFile: openPath,
    pick: (x, y, radius) => currentHost()?.pick({ x, y }, radius ?? 8) ?? [],
    setSelection: (handles) => {
      currentHost()?.setSelection(handles);
      selection.setState({ handles });
    },
    highlight: (handles) => {
      currentHost()?.highlight(handles);
    },
    zoomToFit: () => {
      currentHost()?.zoomToFit();
    },
    layers: () => layers().map((layer) => layer.name),
    layerStates: () =>
      layers().map((layer) => ({
        name: layer.name,
        visible: layer.visible,
        frozen: layer.frozen,
      })),
    setLayerVisible: (name, visible) => currentHost()?.setLayerVisible(name, visible) ?? false,
    setLayersVisible,
    whenRenderIdle,
    populatedLayers: () => {
      const host = currentHost();
      if (!host) return [];
      const names = new Set<string>();
      for (const entity of host.entities()) names.add(entity.layer);
      return [...names].sort();
    },
    close: closeDrawing,
    dispose: disposeCadHost,
    heapUsedBytes: () => {
      const memory = (performance as unknown as { memory?: { usedJSHeapSize?: number } }).memory;
      return typeof memory?.usedJSHeapSize === 'number' ? memory.usedJSHeapSize : null;
    },
    viewerDocumentCount: () => currentHost()?.documents().length ?? 0,
    selectionEvents: () => selectionEvents.map((handles) => [...handles]),
    renderLoad: () => {
      const host = currentHost();
      const document = host?.document();
      if (!document) return { topLevel: 0, inBlocks: 0, total: 0 };
      let topLevel = 0;
      for (const space of document.spaces()) topLevel += count(space.entities());
      let inBlocks = 0;
      for (const block of document.blocks()) {
        if (block.isModelSpace || block.isPaperSpace) continue;
        inBlocks += block.entityCount;
      }
      return { topLevel, inBlocks, total: topLevel + inBlocks };
    },
    collectGarbage: async () => {
      const gc = (globalThis as unknown as { gc?: () => void }).gc;
      if (!gc) return false;
      // Two passes with a macrotask in between: the first drops the documents,
      // the second collects what their finalizers released.
      gc();
      await new Promise((resolve) => setTimeout(resolve, 50));
      gc();
      return true;
    },
  };
  window.__haloViewer = hooks;
}

const container = document.getElementById('root');
if (!container) throw new Error('root element (#root) not found');

createRoot(container).render(
  <StrictMode>
    <div className="h-screen w-screen bg-neutral-950 text-neutral-100">
      <ViewerPanel />
    </div>
  </StrictMode>
);

installTestHooks();
