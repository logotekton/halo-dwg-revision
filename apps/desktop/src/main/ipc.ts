import { app, dialog, ipcMain } from 'electron'
import type { EngineConnection, EngineSupervisor } from './engine'

/**
 * IPC surface for the preload `window.halocad` API
 * (`docs/contracts/wave-2.md`/`docs/contracts/wave-3.md` "IPC 채널").
 * `halocad:app:*` is W1-01's existing API (kept unchanged).
 * `halocad:engine:get-connection` is the only engine invoke channel —
 * status push (`halocad:engine:status`) is wired directly in `index.ts` via
 * `webContents.send`, since it isn't a request/response call.
 * `halocad:files:pick-drawings` is W3-01's addition (below).
 */

const DRAWING_FILE_FILTERS: Electron.FileFilter[] = [{ name: 'CAD 도면 (DWG/DXF)', extensions: ['dwg', 'dxf'] }]

/**
 * Resolves the list of drawing files to open for the "열기" action.
 *
 * Pure w.r.t. Electron: takes `env` and a `showOpenDialog` callback as
 * plain arguments (same shape as `apps/desktop/src/main/protocol.ts`'s
 * `resolveWebDistDir`) instead of importing `dialog`/`process.env`
 * directly, so the branching logic is unit-testable without an Electron
 * runtime.
 *
 * Brief W3-01 Constraints: "pickDrawings는 e2e에서 다이얼로그를 띄우지 않도록
 * HALO_E2E=1일 때 환경변수 HALO_E2E_PICK_FILES(쉼표 구분 경로)를 대신
 * 반환" — Playwright can't drive the native OS file picker, so the e2e
 * harness substitutes a fixed, comma-separated path list instead of ever
 * showing the real dialog.
 */
// A plain index signature (not named optional properties) so both
// `process.env` (also index-signature-typed) and a small literal object in
// tests are assignable without TS's "weak type" excess-property-style
// check getting in the way (that check special-cases object types whose
// properties are *all* optional and does not treat an index signature as
// satisfying it).
export type PickDrawingFilesEnv = Record<string, string | undefined>

export async function pickDrawingFiles(
  env: PickDrawingFilesEnv,
  showOpenDialog: () => Promise<{ canceled: boolean; filePaths: string[] }>,
): Promise<string[]> {
  if (env.HALO_E2E === '1') {
    const fixed = env.HALO_E2E_PICK_FILES
    if (!fixed) return []
    return fixed
      .split(',')
      .map((p) => p.trim())
      .filter((p) => p.length > 0)
  }

  const result = await showOpenDialog()
  return result.canceled ? [] : result.filePaths
}

export function registerIpcHandlers(engine: EngineSupervisor): void {
  ipcMain.handle('halocad:app:getVersion', () => app.getVersion())

  ipcMain.handle(
    'halocad:engine:get-connection',
    async (): Promise<EngineConnection> => engine.getConnection(),
  )

  ipcMain.handle('halocad:files:pick-drawings', async (): Promise<string[]> =>
    pickDrawingFiles(process.env, async () =>
      dialog.showOpenDialog({
        properties: ['openFile', 'multiSelections'],
        filters: DRAWING_FILE_FILTERS,
      }),
    ),
  )
}
