/**
 * The renderer's single {@link CadHost} instance and the glue that keeps the
 * `viewer` / `selection` stores in step with it.
 *
 * `docs/contracts/wave-3.md`: the canvas container is `#viewer-root` and only
 * `apps/web/src/features/viewer/**` may touch `CadHost`. Everything else in the
 * shell reads the stores.
 */

import { CadHost } from '@halo-cad/cad-core';
import type { CadHostWarning, OpenResult } from '@halo-cad/cad-core';
import { selection, viewer } from './viewer-store';

export const VIEWER_ROOT_ID = 'viewer-root';

let host: CadHost | null = null;
let creating: Promise<CadHost> | null = null;

/**
 * Root the viewer assets are served from.
 *
 * In the desktop app this comes from the preload
 * (`window.halocad.viewer.assetsBase()` → `halocad://app/viewer`). In a plain
 * browser dev server the same files sit under `/viewer`, which is what
 * `apps/web/public/viewer` produces, so the fallback keeps `pnpm --filter
 * @halo-cad/web dev` usable without Electron.
 */
async function resolveAssetsBase(): Promise<string> {
  const api = window.halocad as { viewer?: { assetsBase?: () => Promise<string> } } | undefined;
  const fromPreload = await api?.viewer?.assetsBase?.();
  return fromPreload ?? `${window.location.origin}/viewer`;
}

/** Creates the host on first use and wires its events into the stores. */
export async function ensureCadHost(container: HTMLElement): Promise<CadHost> {
  if (host) return host;
  creating ??= (async (): Promise<CadHost> => {
    const created = await CadHost.create({
      container,
      assetsBaseUrl: await resolveAssetsBase(),
      mode: 'write',
    });
    created.on('statusChanged', ({ status }) => {
      viewer.setState((state) => ({ ...state, status }));
    });
    created.on('selectionChanged', ({ handles }) => {
      selection.setState({ handles });
    });
    created.on('documentActivated', ({ fileId }) => {
      viewer.setState((state) => ({ ...state, activeFileId: fileId }));
    });
    created.on('documentClosed', ({ fileId }) => {
      viewer.setState((state) => ({
        ...state,
        documents: state.documents.filter((document) => document.fileId !== fileId),
        activeFileId: state.activeFileId === fileId ? null : state.activeFileId,
      }));
    });
    created.on('openProgress', (progress) => {
      viewer.setState((state) => ({
        ...state,
        progress: { percentage: progress.percentage, stage: progress.stage },
        warnings: mergeWarnings(state.warnings, progress.warnings),
      }));
    });
    created.on('openFailed', ({ message }) => {
      viewer.setState((state) => ({ ...state, error: message }));
    });
    host = created;
    return created;
  })();
  return creating;
}

function mergeWarnings(current: CadHostWarning[], incoming: CadHostWarning[]): CadHostWarning[] {
  const seen = new Set(current.map((warning) => warning.code));
  return [...current, ...incoming.filter((warning) => !seen.has(warning.code))];
}

/** Opens working-DXF bytes and records the result in the `viewer` store. */
export async function openDrawing(
  fileId: string,
  name: string,
  bytes: ArrayBuffer
): Promise<OpenResult> {
  const container = document.getElementById(VIEWER_ROOT_ID);
  if (!container) throw new Error(`#${VIEWER_ROOT_ID} is not mounted`);
  const cadHost = await ensureCadHost(container);
  viewer.setState((state) => ({ ...state, error: null }));
  const result = await cadHost.open(fileId, name, bytes);
  viewer.setState((state) => ({
    ...state,
    activeFileId: result.fileId,
    progress: null,
    warnings: mergeWarnings(state.warnings, result.warnings),
    documents: [
      ...state.documents.filter((document) => document.fileId !== result.fileId),
      {
        fileId: result.fileId,
        name: result.name,
        entityCount: result.entityCount,
        layers: result.layers,
        layouts: result.layouts,
        tier: result.tier,
        durationMs: result.durationMs,
      },
    ],
  }));
  return result;
}

export async function closeDrawing(fileId: string): Promise<void> {
  await host?.close(fileId);
}

export function currentHost(): CadHost | null {
  return host;
}

/** Releases the viewer and its five singletons; used on unmount and by tests. */
export async function disposeCadHost(): Promise<void> {
  const current = host;
  host = null;
  creating = null;
  viewer.setState({
    status: 'idle',
    activeFileId: null,
    documents: [],
    overlays: [],
    warnings: [],
    error: null,
    progress: null,
  });
  selection.setState({ handles: [] });
  await current?.dispose();
}
