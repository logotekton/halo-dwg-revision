import { app, ipcMain } from 'electron'
import type { EngineConnection, EngineSupervisor } from './engine'

/**
 * IPC surface for the preload `window.halocad` API
 * (`docs/contracts/wave-2.md` "IPC 채널"). `halocad:app:*` is W1-01's
 * existing API (kept unchanged). `halocad:engine:get-connection` is the
 * only engine invoke channel — status push (`halocad:engine:status`) is
 * wired directly in `index.ts` via `webContents.send`, since it isn't a
 * request/response call.
 */
export function registerIpcHandlers(engine: EngineSupervisor): void {
  ipcMain.handle('halocad:app:getVersion', () => app.getVersion())

  ipcMain.handle(
    'halocad:engine:get-connection',
    async (): Promise<EngineConnection> => engine.getConnection(),
  )
}
