import { readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { ipcMain } from 'electron'
import type { ConvertJob, DwgConverter } from './index'
import type { ConvertResult } from './protocol'

/**
 * Test-only IPC, registered **only** when the app was started with
 * `HALO_E2E=1` (`docs/contracts/wave-2.md` "테스트 훅").
 *
 * `tests/e2e/viewer.spec.ts` needs three things the production surface does not
 * offer: the fixture paths (`HALO_E2E_PICK_FILES`, standing in for W3-01's
 * native file dialog, which does not exist on this branch), the bytes behind
 * them, and a way to drive the hidden DWG converter. All three are behind this
 * one function so that a normal run registers no file-reading channel at all.
 */
export const E2E_PICK_FILES_CHANNEL = 'halocad:e2e:pick-files'
export const E2E_READ_FILE_CHANNEL = 'halocad:e2e:read-file'
export const E2E_CONVERT_CHANNEL = 'halocad:e2e:convert-dwg'
export const E2E_TMP_PATH_CHANNEL = 'halocad:e2e:tmp-path'

export function isE2eEnabled(): boolean {
  return process.env.HALO_E2E === '1'
}

export function registerE2eBridge(converter: DwgConverter): void {
  if (!isE2eEnabled()) return

  ipcMain.handle(E2E_PICK_FILES_CHANNEL, (): string[] =>
    (process.env.HALO_E2E_PICK_FILES ?? '')
      .split(delimiter)
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0),
  )

  ipcMain.handle(E2E_READ_FILE_CHANNEL, async (_event, path: string): Promise<Uint8Array> => {
    // Readable: the fixtures the harness was started with, plus the converted
    // files this bridge itself produced under the temp directory. Nothing else,
    // so the channel cannot be turned into a general file reader even while the
    // e2e flag is on.
    const allowed = (process.env.HALO_E2E_PICK_FILES ?? '').split(delimiter)
    const isConverted = path.startsWith(tmpPrefix())
    if (!allowed.includes(path) && !isConverted) {
      throw new Error(`e2e: ${path} is neither in HALO_E2E_PICK_FILES nor a converted output`)
    }
    return new Uint8Array(await readFile(path))
  })

  ipcMain.handle(
    E2E_CONVERT_CHANNEL,
    async (_event, job: ConvertJob): Promise<ConvertResult> => converter.convert(job),
  )

  ipcMain.handle(E2E_TMP_PATH_CHANNEL, (_event, name: string): string => `${tmpPrefix()}${name}`)
}

function tmpPrefix(): string {
  return join(tmpdir(), `halo-e2e-${String(process.pid)}-`)
}
