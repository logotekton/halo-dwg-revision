import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { createEngineLogger, startEngineSupervisor, type EngineSupervisor } from '../../src/main/engine'

// apps/desktop/tests/integration -> apps/desktop -> apps -> <repo root> -> engine
const ENGINE_DIR = resolve(__dirname, '../../../../engine')

function spawnCleanEnv(): NodeJS.ProcessEnv {
  // Strip anything an ambient dev shell might have set so this always
  // exercises real spawn mode, never attach mode.
  const { HALO_ENGINE_URL: _url, HALO_ENGINE_TOKEN: _token, HALO_ENGINE_PARENT_PID: _ppid, ...rest } = process.env
  return rest
}

async function waitUntil(
  predicate: () => boolean,
  { timeoutMs, intervalMs = 100 }: { timeoutMs: number; intervalMs?: number },
): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error('waitUntil: condition not met before timeout')
    await new Promise((res) => setTimeout(res, intervalMs))
  }
}

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

describe('engine supervisor (real `uv run halo-engine serve` subprocess)', () => {
  let supervisor: EngineSupervisor | undefined
  let tmpDir: string | undefined

  afterEach(async () => {
    await supervisor?.shutdown()
    supervisor = undefined
    if (tmpDir) {
      await rm(tmpDir, { recursive: true, force: true })
      tmpDir = undefined
    }
  })

  it('spawns, reaches ready, survives a kill via restart on the same port, then shuts down cleanly', async () => {
    tmpDir = await mkdtemp(join(tmpdir(), 'halo-engine-supervisor-'))
    const logger = createEngineLogger(join(tmpDir, 'logs'))

    supervisor = startEngineSupervisor({
      isPackaged: false,
      engineDir: ENGINE_DIR,
      resourcesPath: '',
      dataDir: join(tmpDir, 'engine'),
      logger,
      env: spawnCleanEnv(),
    })

    // ---- spawn -> ready ----
    const connection = await supervisor.getConnection()
    expect(connection.baseUrl).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/)
    expect(connection.token).toMatch(/^[0-9a-f]{64}$/)
    expect(supervisor.getStatus()).toMatchObject({ state: 'ready' })
    const readyPort = supervisor.getStatus().port
    expect(readyPort).toBeGreaterThan(0)

    // ---- health ----
    // (getConnection() already implied one successful health check during
    // startup; also exercise it directly, as apps/web/src/api/engine.ts's
    // engineFetch() would.)
    const healthResponse = await fetch(`${connection.baseUrl}/api/v1/system/health`)
    expect(healthResponse.status).toBe(200)
    const healthBody: unknown = await healthResponse.json()
    expect((healthBody as { status: string }).status).toBe('ok')

    // ---- kill -> restarting -> ready (same port) ----
    // Kill the *server*'s own pid (from the READY handshake), not the pid
    // Node's spawn() returned for the `uv run` wrapper — those two differ in
    // dev mode (uv runs halo_engine as a genuine child process rather than
    // exec-replacing itself; confirmed empirically, and matches the
    // coordinator's Windows CI finding of the same wrapper/server pid split
    // for a packaged `halo-engine.exe` launcher). This is also what a real
    // user killing "the engine" would target — `pgrep -f halo-engine` /
    // Activity Monitor show the server's cmdline, not uv's.
    const firstPids = supervisor.getPid()
    expect(firstPids?.serverPid).toBeDefined()
    const firstServerPid = firstPids!.serverPid!
    expect(firstServerPid).not.toBe(firstPids!.spawnPid)
    process.kill(firstServerPid, 'SIGKILL')

    await waitUntil(() => supervisor?.getStatus().state === 'restarting', { timeoutMs: 5_000 })
    expect(supervisor.getStatus().attempt).toBe(1)

    await waitUntil(() => supervisor?.getStatus().state === 'ready', { timeoutMs: 30_000 })
    expect(supervisor.getStatus().port).toBe(readyPort)

    const secondPids = supervisor.getPid()
    expect(secondPids?.serverPid).toBeDefined()
    const secondServerPid = secondPids!.serverPid!
    expect(secondServerPid).not.toBe(firstServerPid)

    const secondConnection = await supervisor.getConnection()
    const healthAfterRestart = await fetch(`${secondConnection.baseUrl}/api/v1/system/health`)
    expect(healthAfterRestart.status).toBe(200)

    // ---- shutdown ----
    await supervisor.shutdown()
    expect(isProcessAlive(secondPids!.spawnPid)).toBe(false)
    expect(isProcessAlive(secondServerPid)).toBe(false)
  })

  it('restarts cleanly even when only the spawn (wrapper) pid dies, not the server pid (regression guard)', async () => {
    // Reproduces the bug this task found: killing only the `uv` wrapper pid
    // orphans the real server process still holding the port, so the next
    // restart attempt's bind() fails with "Address already in use" unless
    // the exit handler defensively cleans up the whole process group first
    // (apps/desktop/src/main/engine/supervisor.ts's `killTree` call in the
    // `exit` handler).
    tmpDir = await mkdtemp(join(tmpdir(), 'halo-engine-supervisor-'))
    const logger = createEngineLogger(join(tmpDir, 'logs'))

    supervisor = startEngineSupervisor({
      isPackaged: false,
      engineDir: ENGINE_DIR,
      resourcesPath: '',
      dataDir: join(tmpDir, 'engine'),
      logger,
      env: spawnCleanEnv(),
    })

    await supervisor.getConnection()
    const readyPort = supervisor.getStatus().port
    const pids = supervisor.getPid()
    expect(pids?.serverPid).toBeDefined()

    process.kill(pids!.spawnPid, 'SIGKILL')

    await waitUntil(() => supervisor?.getStatus().state === 'restarting', { timeoutMs: 5_000 })
    await waitUntil(() => supervisor?.getStatus().state === 'ready', { timeoutMs: 30_000 })

    expect(supervisor.getStatus().port).toBe(readyPort)
    expect(isProcessAlive(pids!.serverPid!)).toBe(false)

    const connection = await supervisor.getConnection()
    const health = await fetch(`${connection.baseUrl}/api/v1/system/health`)
    expect(health.status).toBe(200)
  })
})
