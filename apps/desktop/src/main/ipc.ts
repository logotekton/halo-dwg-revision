import { app, clipboard, dialog, ipcMain, shell } from 'electron'
import type { EngineConnection, EngineSupervisor } from './engine'

/**
 * IPC surface for the preload `window.halocad` API
 * (`docs/contracts/wave-2.md`/`docs/contracts/wave-3.md` "IPC 채널").
 * `halocad:app:*` is W1-01's existing API (kept unchanged).
 * `halocad:engine:get-connection` is the only engine invoke channel —
 * status push (`halocad:engine:status`) is wired directly in `index.ts` via
 * `webContents.send`, since it isn't a request/response call.
 * `halocad:files:pick-drawings` is W3-01's addition.
 * `halocad:dialog:pick-folder` / `halocad:clipboard:write-text` /
 * `halocad:shell:open-path` are R1-05's addition (docs/contracts/r1.md §8),
 * for screen A's folder pickers and screen B's "도곽 열기"/clipboard
 * actions.
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

/**
 * FIFO state for `pickFolder`'s e2e substitute, module-scoped so repeated
 * `halocad:dialog:pick-folder` invokes (screen A calls it twice: 전 폴더,
 * then 후 폴더) each consume the next entry of `HALO_E2E_PICK_FOLDERS`
 * instead of replaying the first one. `queue` starts `null` (not yet
 * parsed) rather than `[]` so the env var is parsed exactly once per
 * process, on the first call -- a fresh Electron process per e2e test
 * (`packages/testing/src/electron.ts::launchHalo`) means this never needs
 * an explicit reset.
 */
export interface PickFolderQueueState {
  queue: string[] | null
}

/**
 * Resolves one folder pick for `halocad:dialog:pick-folder`. Contract §8:
 * "e2e: `HALO_E2E=1`이면 `HALO_E2E_PICK_FOLDERS`(쉼표 구분)를 앞에서부터
 * 하나씩 소비". Pure w.r.t. Electron (env + a mutable queue holder +
 * `showOpenDialog` callback) for the same testability reason as
 * `pickDrawingFiles` above.
 */
export async function pickFolder(
  env: PickDrawingFilesEnv,
  state: PickFolderQueueState,
  showOpenDialog: () => Promise<{ canceled: boolean; filePaths: string[] }>,
): Promise<string | null> {
  if (env.HALO_E2E === '1') {
    if (state.queue === null) {
      const raw = env.HALO_E2E_PICK_FOLDERS
      state.queue = raw
        ? raw
            .split(',')
            .map((p) => p.trim())
            .filter((p) => p.length > 0)
        : []
    }
    return state.queue.shift() ?? null
  }

  const result = await showOpenDialog()
  if (result.canceled) return null
  return result.filePaths[0] ?? null
}

/**
 * Appends `path` to the comma-separated `HALO_E2E_OPENED_PATHS` env value
 * (contract §8's e2e substitute for `halocad:shell:open-path`: "열지 않고
 * `process.env.HALO_E2E_OPENED_PATHS`에 기록만"). Pure -- returns the next
 * value rather than mutating `env` itself, so `registerIpcHandlers` is the
 * only place that actually writes `process.env`.
 */
export function recordE2EOpenedPath(env: PickDrawingFilesEnv, path: string): string {
  const existing = env.HALO_E2E_OPENED_PATHS
  const opened = existing ? existing.split(',') : []
  opened.push(path)
  return opened.join(',')
}

/**
 * Resolves `halocad:shell:open-path`: the real `shell.openPath` normally,
 * or (under `HALO_E2E=1`) just a record of the attempt -- e2e must never
 * actually spawn the OS file explorer/CAD viewer.
 */
export async function openPath(
  env: PickDrawingFilesEnv,
  path: string,
  shellOpenPath: (path: string) => Promise<string>,
): Promise<void> {
  if (env.HALO_E2E === '1') {
    process.env.HALO_E2E_OPENED_PATHS = recordE2EOpenedPath(env, path)
    return
  }
  const error = await shellOpenPath(path)
  if (error) throw new Error(error)
}

const pickFolderQueueState: PickFolderQueueState = { queue: null }

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

  ipcMain.handle(
    'halocad:dialog:pick-folder',
    async (_event, args: { title?: string } | undefined): Promise<string | null> =>
      pickFolder(process.env, pickFolderQueueState, async () =>
        dialog.showOpenDialog({
          title: args?.title,
          properties: ['openDirectory'],
        }),
      ),
  )

  ipcMain.handle(
    'halocad:clipboard:write-text',
    // `clipboard.writeText` returns `Promise<void>` (electron.d.ts), not `void`.
    async (_event, args: { text: string }): Promise<void> => clipboard.writeText(args.text),
  )

  ipcMain.handle(
    'halocad:shell:open-path',
    async (_event, args: { path: string }): Promise<void> =>
      openPath(process.env, args.path, async (path) => shell.openPath(path)),
  )
}
