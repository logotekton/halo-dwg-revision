/**
 * Health polling against the sidecar's unauthenticated
 * `GET /api/v1/system/health` (`docs/contracts/wave-2.md` "health").
 */
export interface EngineHealth {
  status: string
  version: string
}

export async function fetchHealth(baseUrl: string, signal?: AbortSignal): Promise<EngineHealth> {
  const response = await fetch(`${baseUrl}/api/v1/system/health`, { signal })
  if (!response.ok) {
    throw new Error(`engine health check failed: HTTP ${String(response.status)}`)
  }
  const body: unknown = await response.json()
  if (typeof body !== 'object' || body === null) {
    throw new Error('engine health check returned a non-object body')
  }
  const { status, version } = body as Record<string, unknown>
  if (typeof status !== 'string' || typeof version !== 'string') {
    throw new Error('engine health check returned an unexpected body shape')
  }
  return { status, version }
}

export interface PollHealthOptions {
  /** Delay between poll attempts. */
  intervalMs: number
  /** Total time budget before giving up (`docs/contracts/wave-2.md`: 30s). */
  timeoutMs: number
}

/**
 * Polls `/system/health` until it responds successfully or `timeoutMs`
 * elapses, whichever comes first. Tries immediately, then every
 * `intervalMs`.
 */
export async function pollHealthUntilReady(baseUrl: string, options: PollHealthOptions): Promise<EngineHealth> {
  const deadline = Date.now() + options.timeoutMs
  for (;;) {
    try {
      return await fetchHealth(baseUrl)
    } catch (error) {
      if (Date.now() >= deadline) {
        throw error instanceof Error ? error : new Error(String(error))
      }
      await delay(options.intervalMs)
    }
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}
