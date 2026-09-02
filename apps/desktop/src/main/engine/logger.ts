import { existsSync, mkdirSync, renameSync, unlinkSync } from 'node:fs'
import { appendFile } from 'node:fs/promises'
import { join } from 'node:path'

/**
 * `<userData>/logs/engine.log`: the engine child process's own stdout noise
 * (everything before/after the READY line) and stderr, plus the
 * supervisor's own lifecycle notes (spawn/crash/restart/shutdown), all in
 * one place per the brief's "로그 위치" requirement. Rotates at 5MB, keeping
 * up to 5 files total (the active one plus 4 numbered backups) — see
 * `docs/dev/engine-sidecar.md`.
 *
 * `docs/briefs/W2-01.md` "Defaults for ambiguity" names `electron-log` (MIT)
 * as the logging library to adopt, but adding it as an `apps/desktop`
 * dependency requires editing `apps/desktop/package.json`, which is outside
 * this task's "Files you own" glob (only the `test:integration` script
 * addition there is explicitly permitted). This module is a small
 * dependency-free stand-in with the same externally observable behavior
 * (rotating file transport + console echo); swapping in electron-log is a
 * one-file change once that package.json edit lands — see the report's
 * "Shared-file patch" / "Deviations from brief".
 */
export interface EngineLogger {
  info(message: string): void
  warn(message: string): void
  error(message: string): void
  readonly filePath: string
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
/** Numbered backups kept beyond the active file (4 + active = 5 total, "5MB×5"). */
const MAX_BACKUPS = 4

export function createEngineLogger(logDir: string): EngineLogger {
  const filePath = join(logDir, 'engine.log')
  let dirReady = false
  let pendingSize = 0
  let writeChain: Promise<void> = Promise.resolve()

  function ensureDir(): void {
    if (dirReady) return
    mkdirSync(logDir, { recursive: true })
    dirReady = true
  }

  function rotateIfNeeded(nextLineBytes: number): void {
    ensureDir()
    if (!existsSync(filePath)) {
      pendingSize = 0
      return
    }
    if (pendingSize + nextLineBytes <= MAX_FILE_SIZE_BYTES) return

    const oldest = `${filePath}.${String(MAX_BACKUPS)}`
    if (existsSync(oldest)) unlinkSync(oldest)
    for (let i = MAX_BACKUPS - 1; i >= 1; i -= 1) {
      const from = `${filePath}.${String(i)}`
      if (existsSync(from)) renameSync(from, `${filePath}.${String(i + 1)}`)
    }
    renameSync(filePath, `${filePath}.1`)
    pendingSize = 0
  }

  function write(level: 'INFO' | 'WARN' | 'ERROR', message: string): void {
    const line = `${new Date().toISOString()} ${level} ${message}\n`
    const lineBytes = Buffer.byteLength(line, 'utf8')
    // Serialize writes so rotation and appends from rapid successive log
    // calls (e.g. forwarding many stdout noise lines) never interleave.
    writeChain = writeChain
      .then(() => {
        rotateIfNeeded(lineBytes)
        pendingSize += lineBytes
        return appendFile(filePath, line, 'utf8')
      })
      .catch((error: unknown) => {
        // Last resort: the log file itself is unwritable.
        console.error('[engine] failed to write log file', error)
      })

    const consoleMethod = level === 'ERROR' ? 'error' : level === 'WARN' ? 'warn' : 'log'
    // Mirrors engine output to the terminal running `pnpm dev`.
    console[consoleMethod](`[engine] ${message}`)
  }

  return {
    filePath,
    info: (message) => {
      write('INFO', message)
    },
    warn: (message) => {
      write('WARN', message)
    },
    error: (message) => {
      write('ERROR', message)
    },
  }
}
