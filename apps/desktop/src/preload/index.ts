import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

// Mirrors apps/desktop/src/main/engine/state-machine.ts's EngineStatus and
// docs/contracts/wave-2.md's IPC payload shapes. Not imported from there:
// preload and main are separate electron-vite build entries, and apps/web
// (the other consumer of this shape) is intentionally independent of
// apps/desktop — see apps/desktop/scripts/dev.mjs's top comment. Keep this
// in sync with the contract by hand.
export type EngineState = 'starting' | 'ready' | 'restarting' | 'failed'

export interface EngineStatus {
  state: EngineState
  version?: string
  port?: number
  attempt?: number
  message?: string
}

export interface EngineConnection {
  baseUrl: string
  token: string
}

const ENGINE_STATUS_CHANNEL = 'halocad:engine:status'
const VIEWER_ASSETS_BASE_CHANNEL = 'halocad:viewer:assets-base'

// Minimal API surface per brief W1-01 (app.*) plus W2-01 (engine.*) and
// W3-02 (viewer.*).
const haloApi = {
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('halocad:app:getVersion') as Promise<string>,
    platform: process.platform,
  },
  engine: {
    getConnection: (): Promise<EngineConnection> =>
      ipcRenderer.invoke('halocad:engine:get-connection') as Promise<EngineConnection>,
    onStatus: (callback: (status: EngineStatus) => void): (() => void) => {
      const listener = (_event: IpcRendererEvent, status: EngineStatus): void => {
        callback(status)
      }
      ipcRenderer.on(ENGINE_STATUS_CHANNEL, listener)
      return () => {
        ipcRenderer.removeListener(ENGINE_STATUS_CHANNEL, listener)
      }
    },
  },
  viewer: {
    /**
     * Root the viewer's workers, wasm and fonts are served from
     * (`docs/contracts/wave-3.md` "뷰어 자산 배치"): `halocad://app/viewer/`.
     * Asked over IPC rather than hard-coded in the renderer so a packaged
     * build can move the assets without rebuilding apps/web.
     */
    assetsBase: (): Promise<string> =>
      ipcRenderer.invoke(VIEWER_ASSETS_BASE_CHANNEL) as Promise<string>,
  },
}

export type HaloApi = typeof haloApi

contextBridge.exposeInMainWorld('halocad', haloApi)

// Test-only, not part of the halocad contract: relays HALO_E2E so renderer
// code (apps/web/src/test-hooks.ts) can gate window.__haloTest on it without
// leaking process.env itself into the renderer's main world
// (docs/contracts/wave-2.md "테스트 훅").
contextBridge.exposeInMainWorld('__HALO_E2E_ENABLED__', process.env.HALO_E2E === '1')

// Viewer e2e bridge (W3-02), likewise test-only and gated the same way. It
// gives tests/e2e/viewer.spec.ts the fixture paths from HALO_E2E_PICK_FILES,
// their bytes, and the hidden DWG converter. The matching main-process
// handlers exist only when HALO_E2E=1 (apps/desktop/src/main/convert/e2e.ts),
// so exposing the functions here can never widen the production surface.
if (process.env.HALO_E2E === '1') {
  contextBridge.exposeInMainWorld('__haloViewerTest', {
    pickFiles: (): Promise<string[]> =>
      ipcRenderer.invoke('halocad:e2e:pick-files') as Promise<string[]>,
    readFile: (path: string): Promise<Uint8Array> =>
      ipcRenderer.invoke('halocad:e2e:read-file', path) as Promise<Uint8Array>,
    convertDwg: (job: { dwgPath: string; outPath: string }): Promise<unknown> =>
      ipcRenderer.invoke('halocad:e2e:convert-dwg', job),
    tmpPath: (name: string): Promise<string> =>
      ipcRenderer.invoke('halocad:e2e:tmp-path', name) as Promise<string>,
  })
}
