import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EngineConnection } from './types'

function mockHalocad(getConnection: () => Promise<EngineConnection>): void {
  Object.defineProperty(window, 'halocad', {
    configurable: true,
    value: {
      app: { getVersion: vi.fn(), platform: 'darwin' },
      engine: { getConnection, onStatus: vi.fn(() => () => undefined) },
    },
  })
}

describe('getEngine', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  it('memoizes the connection: window.halocad.engine.getConnection() is invoked at most once', async () => {
    const connection: EngineConnection = { baseUrl: 'http://127.0.0.1:54213', token: 'tok' }
    const getConnection = vi.fn().mockResolvedValue(connection)
    mockHalocad(getConnection)

    const { getEngine } = await import('./engine')
    const first = await getEngine()
    const second = await getEngine()

    expect(first).toBe(connection)
    expect(second).toBe(connection)
    expect(getConnection).toHaveBeenCalledTimes(1)
  })

  it('a fresh module (new renderer session) calls getConnection again', async () => {
    const getConnectionA = vi.fn().mockResolvedValue({ baseUrl: 'http://127.0.0.1:1', token: 'a' })
    mockHalocad(getConnectionA)
    const moduleA = await import('./engine')
    await moduleA.getEngine()

    vi.resetModules()
    const getConnectionB = vi.fn().mockResolvedValue({ baseUrl: 'http://127.0.0.1:2', token: 'b' })
    mockHalocad(getConnectionB)
    const moduleB = await import('./engine')
    await moduleB.getEngine()

    expect(getConnectionA).toHaveBeenCalledTimes(1)
    expect(getConnectionB).toHaveBeenCalledTimes(1)
  })
})

describe('engineFetch', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('joins baseUrl+path and attaches the bearer token from getConnection()', async () => {
    mockHalocad(() => Promise.resolve({ baseUrl: 'http://127.0.0.1:54213', token: 'secret-token' }))
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { engineFetch } = await import('./engine')
    await engineFetch('/api/v1/system/health')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('http://127.0.0.1:54213/api/v1/system/health')
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer secret-token')
  })

  it('preserves caller-provided init (method/body) alongside the auth header', async () => {
    mockHalocad(() => Promise.resolve({ baseUrl: 'http://127.0.0.1:54213', token: 't' }))
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { engineFetch } = await import('./engine')
    await engineFetch('/api/v1/system/shutdown', { method: 'POST' })

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect((init.headers as Headers).get('Authorization')).toBe('Bearer t')
  })

  it('propagates a getConnection() rejection instead of calling fetch', async () => {
    mockHalocad(() => Promise.reject(new Error('engine failed to start')))
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { engineFetch } = await import('./engine')
    await expect(engineFetch('/api/v1/system/health')).rejects.toThrow('engine failed to start')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
