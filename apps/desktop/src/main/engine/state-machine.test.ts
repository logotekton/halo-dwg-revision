import { describe, expect, it } from 'vitest'
import { INITIAL_ENGINE_STATUS, reduceEngineStatus, type EngineStatus } from './state-machine'

describe('reduceEngineStatus', () => {
  it('starts in the starting state', () => {
    expect(INITIAL_ENGINE_STATUS).toEqual({ state: 'starting' })
  })

  it('transitions starting -> ready on the first READY+health success', () => {
    const next = reduceEngineStatus(INITIAL_ENGINE_STATUS, { type: 'ready', version: '0.0.1', port: 54213 })
    expect(next).toEqual({ state: 'ready', version: '0.0.1', port: 54213 })
  })

  it('walks the full crash → restart × 3 → failed sequence (docs/contracts/wave-2.md)', () => {
    let status: EngineStatus = INITIAL_ENGINE_STATUS
    status = reduceEngineStatus(status, { type: 'ready', version: '0.0.1', port: 111 })
    expect(status).toEqual({ state: 'ready', version: '0.0.1', port: 111 })

    // crash -> restarting, attempt 1
    status = reduceEngineStatus(status, { type: 'restart-scheduled', attempt: 1 })
    expect(status).toEqual({ state: 'restarting', attempt: 1 })

    // successful reconnect resets to ready
    status = reduceEngineStatus(status, { type: 'ready', version: '0.0.1', port: 111 })
    expect(status).toEqual({ state: 'ready', version: '0.0.1', port: 111 })

    // crashes again, three consecutive failed restarts, then give up
    status = reduceEngineStatus(status, { type: 'restart-scheduled', attempt: 1 })
    expect(status).toEqual({ state: 'restarting', attempt: 1 })
    status = reduceEngineStatus(status, { type: 'restart-scheduled', attempt: 2 })
    expect(status).toEqual({ state: 'restarting', attempt: 2 })
    status = reduceEngineStatus(status, { type: 'restart-scheduled', attempt: 3 })
    expect(status).toEqual({ state: 'restarting', attempt: 3 })
    status = reduceEngineStatus(status, { type: 'failed', message: '엔진을 3회 재시작했지만 계속 실패했습니다. 로그: /tmp/engine.log' })
    expect(status).toEqual({
      state: 'failed',
      message: '엔진을 3회 재시작했지만 계속 실패했습니다. 로그: /tmp/engine.log',
    })
  })

  it('goes straight to failed when the engine can never be spawned (e.g. uv missing)', () => {
    const status = reduceEngineStatus(INITIAL_ENGINE_STATUS, {
      type: 'failed',
      message: 'uv가 설치되어 있지 않습니다.',
    })
    expect(status).toEqual({ state: 'failed', message: 'uv가 설치되어 있지 않습니다.' })
  })

  it('a restarting status carries no stale version/port from the prior ready state', () => {
    const ready = reduceEngineStatus(INITIAL_ENGINE_STATUS, { type: 'ready', version: '0.0.1', port: 111 })
    const restarting = reduceEngineStatus(ready, { type: 'restart-scheduled', attempt: 1 })
    expect(restarting.version).toBeUndefined()
    expect(restarting.port).toBeUndefined()
  })
})
