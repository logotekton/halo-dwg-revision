import { app, ipcMain } from 'electron'

/**
 * Minimal IPC surface for the preload `window.halocad.app` API. Engine/sidecar
 * IPC (system health, jobs, model.changed, ...) is added by W2-01; keep this
 * file scoped to what W1-01's preload bridge actually exposes today.
 */
export function registerIpcHandlers(): void {
  ipcMain.handle('halocad:app:getVersion', () => app.getVersion())
}
