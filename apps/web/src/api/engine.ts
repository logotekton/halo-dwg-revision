// window.halocad's type comes from the ambient declaration in ./halocad.d.ts
// (picked up automatically via tsconfig's "include": ["src"] — no import needed).
import type { EngineConnection } from './types'

export type { EngineConnection, EngineState, EngineStatus } from './types'

/**
 * `window.halocad.engine.getConnection()`'s result, memoized for the life
 * of this renderer session (`docs/contracts/wave-2.md`: "렌더러 세션당 1회
 * 호출"). Re-running `getEngine()` after a rejection re-uses the same
 * rejected promise rather than retrying — the status bar (driven by
 * `onStatus`) is the source of truth for "should the user retry", not this
 * module.
 */
let connectionPromise: Promise<EngineConnection> | undefined

export function getEngine(): Promise<EngineConnection> {
  connectionPromise ??= window.halocad.engine.getConnection()
  return connectionPromise
}

/**
 * `fetch` against the engine sidecar with the bearer token attached
 * automatically. `path` should include the leading slash and API prefix,
 * e.g. `engineFetch('/api/v1/system/health')`.
 */
export async function engineFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { baseUrl, token } = await getEngine()
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${baseUrl}${path}`, { ...init, headers })
}
