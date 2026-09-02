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

// Minimal API surface per brief W1-01 (app.*) plus W2-01 (engine.*).
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
}

export type HaloApi = typeof haloApi

contextBridge.exposeInMainWorld('halocad', haloApi)

// Test-only, not part of the halocad contract: relays HALO_E2E so renderer
// code (apps/web/src/test-hooks.ts) can gate window.__haloTest on it without
// leaking process.env itself into the renderer's main world
// (docs/contracts/wave-2.md "테스트 훅").
contextBridge.exposeInMainWorld('__HALO_E2E_ENABLED__', process.env.HALO_E2E === '1')
