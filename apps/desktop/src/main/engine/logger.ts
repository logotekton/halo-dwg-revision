import { mkdirSync } from 'node:fs'
import { join } from 'node:path'
import log from 'electron-log/node'

/**
 * `<userData>/logs/engine.log`: the engine child process's own stdout noise
 * (everything before/after the READY line) and stderr, plus the
 * supervisor's own lifecycle notes (spawn/crash/restart/shutdown), all in
 * one place per the brief's "로그 위치" requirement — see
 * `docs/dev/engine-sidecar.md`.
 *
 * Built on `electron-log` (MIT), per `docs/briefs/W2-01.md`'s "Defaults for
 * ambiguity". W2-01 shipped a small dependency-free stand-in instead
 * (same externally observable behavior: a rotating file transport plus a
 * `[engine] <message>` console echo) because adding the real dependency
 * needed an `apps/desktop/package.json` edit outside that task's "Files you
 * own" glob; W3-08 lands the dependency and this module now wraps it
 * directly, keeping the same `EngineLogger` interface so every caller
 * (`supervisor.ts`, `apps/desktop/src/main/index.ts`,
 * `tests/integration/engine-supervisor.test.ts`) is unchanged.
 *
 * `electron-log/node` (not the plain default export, which assumes a real
 * `app` singleton) works identically inside the real Electron main process
 * and under plain Node (this module's own tests, and the integration test
 * above, run outside Electron). Each call gets its own independent
 * `log.create({logId})` instance with a fresh, process-unique `logId`, so
 * concurrent callers targeting different `logDir`s (as the tests do, one
 * fresh temp directory per test) never share a file target or rotation
 * state — `electron-log` keeps created instances in a process-wide registry
 * keyed by `logId` purely for lookup; a fresh id per call keeps that
 * registry from being a hidden channel between otherwise-independent loggers.
 *
 * Rotation itself is `electron-log`'s own default behavior (size-triggered,
 * `maxSize` set to the same 5MB threshold this module always used) rather
 * than the previous stand-in's hand-rolled 5-numbered-backups scheme —
 * nothing in this codebase depends on the exact backup count or the log
 * line's on-disk format, only on `filePath` (a plain path string) and the
 * `info`/`warn`/`error` methods, both preserved exactly.
 */
export interface EngineLogger {
  info(message: string): void
  warn(message: string): void
  error(message: string): void
  readonly filePath: string
}

const MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024

let instanceCounter = 0

export function createEngineLogger(logDir: string): EngineLogger {
  mkdirSync(logDir, { recursive: true })
  const filePath = join(logDir, 'engine.log')

  const instance = log.create({
    logId: `engine-${String(process.pid)}-${String(instanceCounter++)}`,
  })
  instance.transports.file.resolvePathFn = () => filePath
  instance.transports.file.maxSize = MAX_FILE_SIZE_BYTES
  // electron-log's own console transport formats lines as
  // `[HH:mm:ss.mmm] [level] message`; this module keeps the exact
  // `[engine] <message>` mirror `pnpm dev`'s terminal has always shown
  // instead (below), so the built-in console transport is silenced.
  instance.transports.console.level = false

  function write(level: 'info' | 'warn' | 'error', message: string): void {
    instance[level](message)
    const consoleMethod = level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'log'
    // Mirrors engine output to the terminal running `pnpm dev`.
    console[consoleMethod](`[engine] ${message}`)
  }

  return {
    filePath,
    info: (message) => {
      write('info', message)
    },
    warn: (message) => {
      write('warn', message)
    },
    error: (message) => {
      write('error', message)
    },
  }
}
