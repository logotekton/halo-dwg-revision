/**
 * Engine connection state machine (`docs/contracts/wave-2.md` "상태 머신":
 * `starting → ready → (crashed → restarting)×3 → failed`). This module is a
 * pure reducer — all process/IO side effects (spawning, polling, timers)
 * live in `supervisor.ts`, which drives this reducer and forwards its output
 * verbatim as the `halocad:engine:status` IPC payload.
 */
export type EngineState = 'starting' | 'ready' | 'restarting' | 'failed'

export interface EngineStatus {
  state: EngineState
  version?: string
  port?: number
  attempt?: number
  message?: string
}

export const INITIAL_ENGINE_STATUS: EngineStatus = { state: 'starting' }

export type EngineEvent =
  | { type: 'ready'; version: string; port?: number }
  | { type: 'restart-scheduled'; attempt: number }
  | { type: 'failed'; message: string }

/**
 * Applies one event to the current status, returning the next one. Pure:
 * same inputs always produce the same output, no I/O.
 */
export function reduceEngineStatus(_current: EngineStatus, event: EngineEvent): EngineStatus {
  switch (event.type) {
    case 'ready':
      return { state: 'ready', version: event.version, port: event.port }
    case 'restart-scheduled':
      return { state: 'restarting', attempt: event.attempt }
    case 'failed':
      return { state: 'failed', message: event.message }
    default: {
      const exhaustive: never = event
      throw new Error(`unhandled engine event: ${JSON.stringify(exhaustive)}`)
    }
  }
}
