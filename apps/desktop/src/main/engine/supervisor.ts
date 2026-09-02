import { randomBytes } from 'node:crypto'
import { spawn as spawnProcess, type ChildProcessByStdio } from 'node:child_process'
import { existsSync } from 'node:fs'
import type { Readable } from 'node:stream'

import { backoffDelayMs, MAX_RESTART_ATTEMPTS } from './backoff'
import { pollHealthUntilReady } from './health'
import type { EngineLogger } from './logger'
import { waitForReady } from './ready'
import { resolveEngineCommand } from './spawn'
import { INITIAL_ENGINE_STATUS, reduceEngineStatus, type EngineStatus } from './state-machine'

/** Our spawn() call below fixes stdio to ['ignore', 'pipe', 'pipe']. */
type EngineChildProcess = ChildProcessByStdio<null, Readable, Readable>

const READY_TIMEOUT_MS = 30_000
const HEALTH_POLL_INTERVAL_MS = 500
const HEALTH_POLL_TIMEOUT_MS = 30_000
const SHUTDOWN_HTTP_TIMEOUT_MS = 4_000
const SHUTDOWN_GRACE_MS = 5_000

export interface EngineConnection {
  baseUrl: string
  token: string
}

export interface EngineSupervisorOptions {
  isPackaged: boolean
  /** Dev mode only: the `engine/` directory `uv run` runs from. */
  engineDir: string
  /** Packaged mode only: `process.resourcesPath`. */
  resourcesPath: string
  /** `<userData>/engine` — passed to the sidecar as `--data-dir`. */
  dataDir: string
  logger: EngineLogger
  env?: NodeJS.ProcessEnv
}

/**
 * Dev mode's `uv run halo-engine serve` and (per the coordinator's Windows
 * CI findings, `docs/dev/ci.md` on main) a packaged Windows `halo-engine.exe`
 * launcher both spawn the real sidecar as a *child* process rather than
 * exec-replacing themselves — so `spawnPid` (what `child_process.spawn()`
 * returns) and `serverPid` (the READY handshake's `pid`, actually bound to
 * `port`) can differ. Killing only `spawnPid` as a single process can orphan
 * `serverPid` holding the port; see `docs/dev/engine-sidecar.md`.
 */
export interface EngineProcessIds {
  spawnPid: number
  /** `undefined` until the current attempt's READY line has been parsed. */
  serverPid: number | undefined
}

export interface EngineSupervisor {
  /** Resolves once the engine is first reachable; rejects if it never becomes reachable at all. */
  getConnection: () => Promise<EngineConnection>
  /** Synchronous snapshot of the current status. */
  getStatus: () => EngineStatus
  /** Subscribes to status changes; returns an unsubscribe function. Does not replay the current status. */
  onStatus: (listener: (status: EngineStatus) => void) => () => void
  /** The current process ids (spawn mode only), or `null` if not currently spawned/attached. Ops/test use only — not part of the IPC contract. */
  getPid: () => EngineProcessIds | null
  /** Best-effort graceful shutdown (POST /shutdown, wait, then SIGTERM/taskkill). Idempotent. */
  shutdown: () => Promise<void>
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function waitForExit(child: EngineChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true)
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.off('exit', onExit)
      resolve(false)
    }, timeoutMs)
    function onExit(): void {
      clearTimeout(timer)
      resolve(true)
    }
    child.once('exit', onExit)
  })
}

function isNoSuchProcessError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'code' in error && error.code === 'ESRCH'
}

/**
 * Kills the engine's whole process tree (constraint: "자식 트리까지 정리"),
 * not just `child`'s own pid — see `EngineProcessIds`'s doc comment on why a
 * single-pid kill can leave the real server process orphaned holding the
 * port. Safe to call after `child` has already exited (its `.pid` is still
 * readable, and on POSIX a process *group* stays signalable as long as any
 * member of it is still alive) — used both for the shutdown grace-period
 * fallback and for defensive post-crash cleanup.
 */
function killTree(child: EngineChildProcess, logger: EngineLogger, signal: NodeJS.Signals = 'SIGTERM'): void {
  if (child.pid === undefined) return

  if (process.platform === 'win32') {
    spawnProcess('taskkill', ['/pid', String(child.pid), '/T', '/F']).on('error', (error: unknown) => {
      logger.warn(`taskkill failed: ${errorMessage(error)}`)
    })
    return
  }

  try {
    // Spawned with detached:true, so the child is its own process group
    // leader — signaling -pid reaches the whole tree (e.g. uv and the
    // actual halo_engine process uv launches as a child), not just the
    // immediate spawned process.
    process.kill(-child.pid, signal)
  } catch (error) {
    // ESRCH here just means the whole group is already gone (the common
    // case for defensive post-crash cleanup) — not worth a warning.
    if (!isNoSuchProcessError(error)) {
      logger.warn(`process group ${signal} failed, falling back to direct kill: ${errorMessage(error)}`)
    }
    child.kill(signal)
  }
}

export function startEngineSupervisor(options: EngineSupervisorOptions): EngineSupervisor {
  const env = options.env ?? process.env
  const { logger } = options

  let status: EngineStatus = INITIAL_ENGINE_STATUS
  let child: EngineChildProcess | null = null
  /** The sidecar's own pid (READY handshake), distinct from `child.pid` — see `EngineProcessIds`. */
  let serverPid: number | undefined
  let stablePort: number | undefined
  let intentionalShutdown = false
  let restartTimer: ReturnType<typeof setTimeout> | null = null
  let currentConnection: EngineConnection | null = null

  const statusListeners = new Set<(status: EngineStatus) => void>()
  let settleConnection: ((connection: EngineConnection) => void) | null = null
  let failConnection: ((error: Error) => void) | null = null
  const connectionPromise = new Promise<EngineConnection>((resolve, reject) => {
    settleConnection = resolve
    failConnection = reject
  })

  function setStatus(next: EngineStatus): void {
    status = next
    for (const listener of statusListeners) listener(next)
  }

  function resolveConnectionOnce(connection: EngineConnection): void {
    currentConnection = connection
    settleConnection?.(connection)
    settleConnection = null
    failConnection = null
  }

  function rejectConnectionOnce(error: Error): void {
    failConnection?.(error)
    settleConnection = null
    failConnection = null
  }

  // ---- Attach mode (docs/contracts/wave-2.md "부착 모드") ----
  // HALO_ENGINE_URL set: never spawn or restart, only poll health.
  function runAttachMode(baseUrl: string, token: string): void {
    void (async () => {
      try {
        const health = await pollHealthUntilReady(baseUrl, {
          intervalMs: HEALTH_POLL_INTERVAL_MS,
          timeoutMs: HEALTH_POLL_TIMEOUT_MS,
        })
        const port = Number(new URL(baseUrl).port) || undefined
        logger.info(`attached to external engine at ${baseUrl} (v${health.version})`)
        setStatus(reduceEngineStatus(status, { type: 'ready', version: health.version, port }))
        resolveConnectionOnce({ baseUrl, token })
      } catch (error) {
        const message = `외부 엔진(${baseUrl})에 연결할 수 없습니다: ${errorMessage(error)}`
        logger.error(message)
        setStatus(reduceEngineStatus(status, { type: 'failed', message }))
        rejectConnectionOnce(new Error(message))
      }
    })()
  }

  // ---- Spawn mode ----
  const token = randomBytes(32).toString('hex')

  function spawnChild(port: number | undefined): EngineChildProcess | { failed: string } {
    const resolved = resolveEngineCommand({
      isPackaged: options.isPackaged,
      engineDir: options.engineDir,
      resourcesPath: options.resourcesPath,
      dataDir: options.dataDir,
      port,
      homeDir: env.HOME ?? env.USERPROFILE ?? '',
      platform: process.platform,
      pathEnv: env.PATH ?? env.Path ?? '',
      fileExists: existsSync,
    })
    if (!resolved.ok) return { failed: resolved.message }

    logger.info(`spawning engine: ${resolved.command} ${resolved.args.join(' ')} (cwd=${resolved.cwd})`)
    return spawnProcess(resolved.command, resolved.args, {
      cwd: resolved.cwd,
      env: {
        ...env,
        HALO_ENGINE_TOKEN: token,
        HALO_ENGINE_PARENT_PID: String(process.pid),
        PYTHONUTF8: '1',
      },
      // Own process group on POSIX so shutdown can signal the whole tree
      // (uv's own child, the actual halo_engine process) via killTree().
      detached: process.platform !== 'win32',
      stdio: ['ignore', 'pipe', 'pipe'],
    })
  }

  function attachNoiseForwarding(proc: EngineChildProcess): void {
    proc.stderr.setEncoding('utf8')
    let stderrBuffer = ''
    proc.stderr.on('data', (chunk: string) => {
      stderrBuffer += chunk
      const lines = stderrBuffer.split('\n')
      stderrBuffer = lines.pop() ?? ''
      for (const line of lines) if (line.length > 0) logger.info(line)
    })
  }

  function scheduleRestart(attempt: number): void {
    const waitMs = backoffDelayMs(attempt)
    if (waitMs === null) {
      const message = `엔진을 ${String(MAX_RESTART_ATTEMPTS)}회 재시작했지만 계속 실패했습니다. 로그: ${logger.filePath}`
      logger.error(message)
      setStatus(reduceEngineStatus(status, { type: 'failed', message }))
      rejectConnectionOnce(new Error(message))
      return
    }
    logger.warn(
      `engine crashed, restarting in ${String(waitMs)}ms (attempt ${String(attempt)}/${String(MAX_RESTART_ATTEMPTS)})`,
    )
    setStatus(reduceEngineStatus(status, { type: 'restart-scheduled', attempt }))
    restartTimer = setTimeout(() => {
      restartTimer = null
      if (intentionalShutdown) return
      void runSpawnAttempt(attempt)
    }, waitMs)
  }

  async function runSpawnAttempt(restartAttempt: number): Promise<void> {
    const spawned = spawnChild(stablePort)
    if ('failed' in spawned) {
      logger.error(spawned.failed)
      setStatus(reduceEngineStatus(status, { type: 'failed', message: spawned.failed }))
      rejectConnectionOnce(new Error(spawned.failed))
      return
    }
    child = spawned
    serverPid = undefined
    attachNoiseForwarding(spawned)

    spawned.on('exit', (code, signal) => {
      if (intentionalShutdown) return
      logger.warn(`engine process exited unexpectedly (code=${String(code)}, signal=${String(signal)})`)
      // Defensive cleanup: on a dev `uv run` spawn (and per the coordinator's
      // Windows CI findings, a packaged Windows launcher too) the exited
      // process can be a *wrapper* whose real server child is still alive
      // and holding the port — see EngineProcessIds's doc comment. This is
      // a best-effort group-kill; the common case (wrapper and server died
      // together) hits ESRCH and is silently ignored by killTree().
      killTree(spawned, logger, 'SIGKILL')
      scheduleRestart(restartAttempt + 1)
    })

    try {
      const ready = await waitForReady(spawned.stdout, {
        timeoutMs: READY_TIMEOUT_MS,
        onNoise: (line) => {
          logger.info(line)
        },
      })
      stablePort = ready.port
      serverPid = ready.pid
      const baseUrl = `http://127.0.0.1:${String(ready.port)}`
      await pollHealthUntilReady(baseUrl, { intervalMs: HEALTH_POLL_INTERVAL_MS, timeoutMs: HEALTH_POLL_TIMEOUT_MS })

      logger.info(`engine ready: pid=${String(ready.pid)} port=${String(ready.port)} version=${ready.version}`)
      setStatus(reduceEngineStatus(status, { type: 'ready', version: ready.version, port: ready.port }))
      resolveConnectionOnce({ baseUrl, token })
    } catch (error) {
      // READY never arrived, or health never came up once it did: treat the
      // same as a crash for restart-counting purposes.
      logger.error(`engine failed to become ready: ${errorMessage(error)}`)
      if (spawned.exitCode === null && spawned.signalCode === null) {
        spawned.removeAllListeners('exit')
        killTree(spawned, logger)
      }
      if (!intentionalShutdown) scheduleRestart(restartAttempt + 1)
    }
  }

  if (env.HALO_ENGINE_URL) {
    const attachToken = env.HALO_ENGINE_TOKEN
    if (!attachToken) {
      const message = 'HALO_ENGINE_URL이 설정되었지만 HALO_ENGINE_TOKEN이 없습니다.'
      logger.error(message)
      setStatus(reduceEngineStatus(status, { type: 'failed', message }))
      rejectConnectionOnce(new Error(message))
    } else {
      runAttachMode(env.HALO_ENGINE_URL, attachToken)
    }
  } else {
    void runSpawnAttempt(0)
  }

  return {
    getConnection: () => connectionPromise,
    getStatus: () => status,
    onStatus: (listener) => {
      statusListeners.add(listener)
      return () => {
        statusListeners.delete(listener)
      }
    },
    getPid: () => (child?.pid === undefined ? null : { spawnPid: child.pid, serverPid }),
    shutdown: async () => {
      if (intentionalShutdown) return
      intentionalShutdown = true
      if (restartTimer) {
        clearTimeout(restartTimer)
        restartTimer = null
      }

      // Attach mode (docs/contracts/wave-2.md "부착 모드"): we never spawned
      // this engine, so we don't own its lifecycle — quitting Electron must
      // not stop a possibly shared/long-running external engine the user
      // started themselves in another terminal.
      const isAttachMode = Boolean(env.HALO_ENGINE_URL)

      if (currentConnection && !isAttachMode) {
        try {
          const controller = new AbortController()
          const timer = setTimeout(() => {
            controller.abort()
          }, SHUTDOWN_HTTP_TIMEOUT_MS)
          await fetch(`${currentConnection.baseUrl}/api/v1/system/shutdown`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${currentConnection.token}` },
            signal: controller.signal,
          })
          clearTimeout(timer)
        } catch (error) {
          logger.warn(`graceful shutdown request failed: ${errorMessage(error)}`)
        }
      }

      const activeChild = child
      if (activeChild?.exitCode === null && activeChild.signalCode === null) {
        const exited = await waitForExit(activeChild, SHUTDOWN_GRACE_MS)
        if (!exited) {
          logger.warn('engine did not exit within the shutdown grace period, killing process tree')
          killTree(activeChild, logger)
          await waitForExit(activeChild, SHUTDOWN_GRACE_MS)
        }
      }
    },
  }
}
