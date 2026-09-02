import { contextBridge, ipcRenderer } from 'electron'

// Minimal API surface per brief W1-01. Engine/sidecar connection
// (window.dmcad.engine.getConnection()) is added by W2-01.
const dmcadApi = {
  app: {
    getVersion: (): Promise<string> => ipcRenderer.invoke('dmcad:app:getVersion') as Promise<string>,
    platform: process.platform,
  },
}

export type DmcadApi = typeof dmcadApi

contextBridge.exposeInMainWorld('dmcad', dmcadApi)
