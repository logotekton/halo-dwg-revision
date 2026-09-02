import { contextBridge, ipcRenderer } from 'electron'

// Minimal API surface per brief W1-01. Engine/sidecar connection
// (window.halocad.engine.getConnection()) is added by W2-01.
const haloApi = {
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('halocad:app:getVersion') as Promise<string>,
    platform: process.platform,
  },
}

export type HaloApi = typeof haloApi

contextBridge.exposeInMainWorld('halocad', haloApi)
