/**
 * Shapes matching `docs/contracts/wave-2.md`'s IPC payloads exactly. Not
 * imported from `apps/desktop` — apps/web is intentionally independent of
 * apps/desktop (see `apps/desktop/scripts/dev.mjs`'s top comment), so this
 * is a hand-kept duplicate of `apps/desktop/src/main/engine/state-machine.ts`
 * / `apps/desktop/src/preload/index.ts`.
 */
export type EngineState = 'starting' | 'ready' | 'restarting' | 'failed'

export interface EngineStatus {
  state: EngineState
  version?: string
  port?: number
  attempt?: number
  message?: string
}

export interface EngineConnection {
  baseUrl: string
  token: string
}
