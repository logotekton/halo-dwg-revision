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
import { closeDrawing, currentHost, disposeCadHost, openDrawing } from './host';
import { selection, viewer } from './viewer-store';

interface ConvertResult {
  dxf_path: string;
  entity_count: number;
  converter: string;
  warnings: string[];
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
  openFile(path: string): Promise<{ fileId: string; converter: string; entityCount: number }>;
  pick(x: number, y: number, radius?: number): string[];
  setSelection(handles: string[]): void;
  highlight(handles: string[]): void;
  zoomToFit(): void;
  /** Every layer in the layer table. */
  layers(): string[];
  /** Layers that actually carry a top-level entity, sorted. */
  populatedLayers(): string[];
  close(fileId: string): Promise<void>;
  dispose(): Promise<void>;
  heapUsedBytes(): number | null;
  /** How many documents the host still tracks. */
  viewerDocumentCount(): number;
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

async function openPath(path: string): Promise<{
  fileId: string;
  converter: string;
  entityCount: number;
}> {
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
    return { fileId, converter: result.converter, entityCount: opened.entityCount };
  }

  const bytes = await bridge.readFile(path);
  const opened = await openDrawing(fileId, name, toArrayBuffer(bytes));
  return { fileId, converter: 'none', entityCount: opened.entityCount };
}

function installTestHooks(): void {
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
    layers: () => (currentHost()?.layers() ?? []).map((layer) => layer.name),
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
