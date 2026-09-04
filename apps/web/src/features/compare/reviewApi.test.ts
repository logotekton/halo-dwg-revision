import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EngineHttpError } from './api'

const engine = vi.hoisted(() => ({ engineFetch: vi.fn() }))
vi.mock('../../api/engine', () => ({ engineFetch: engine.engineFetch }))

const { getClusters, getCompareDxf, patchCluster } = await import('./reviewApi')

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
}

describe('reviewApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getClusters requests the pair sidecar and returns it verbatim', async () => {
    const sidecar = { pair_id: 'p1', clusters: [], counts: { clusters: 0 } }
    engine.engineFetch.mockResolvedValueOnce(jsonResponse(sidecar))

    await expect(getClusters('p1')).resolves.toMatchObject({ pair_id: 'p1' })
    expect(engine.engineFetch).toHaveBeenCalledWith('/api/v1/compare/pairs/p1/clusters')
  })

  it('getClusters throws EngineHttpError with the engine status (409 before a compare)', async () => {
    engine.engineFetch.mockResolvedValueOnce(new Response('not compared', { status: 409 }))

    await expect(getClusters('p1')).rejects.toBeInstanceOf(EngineHttpError)
  })

  it('patchCluster PATCHes only the fields it was given', async () => {
    engine.engineFetch.mockResolvedValueOnce(jsonResponse({ number: 2, decision: 'approved' }))

    await expect(patchCluster('p1', 2, { decision: 'approved' })).resolves.toMatchObject({
      decision: 'approved',
    })
    const call = engine.engineFetch.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/compare/pairs/p1/clusters/2')
    expect(call[1].method).toBe('PATCH')
    expect(call[1].body).toBe('{"decision":"approved"}')
  })

  it('patchCluster sends an explicit null to clear a label', async () => {
    engine.engineFetch.mockResolvedValueOnce(jsonResponse({ number: 1, user_label: null }))

    await patchCluster('p1', 1, { user_label: null })

    const call = engine.engineFetch.mock.calls[0] as [string, RequestInit]
    expect(call[1].body).toBe('{"user_label":null}')
  })

  it('getCompareDxf returns the bytes and the ETag', async () => {
    engine.engineFetch.mockResolvedValueOnce(
      new Response(new Uint8Array([48, 10]), { status: 200, headers: { ETag: '"abc"' } }),
    )

    const result = await getCompareDxf('p1')

    expect(result.notModified).toBe(false)
    expect(result.etag).toBe('"abc"')
    expect(result.bytes?.byteLength).toBe(2)
    const call = engine.engineFetch.mock.calls[0] as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/compare/pairs/p1/compare-dxf')
    expect(call[1].headers).toEqual({})
  })

  it('getCompareDxf sends If-None-Match and reports a 304 without bytes', async () => {
    engine.engineFetch.mockResolvedValueOnce(new Response(null, { status: 304 }))

    const result = await getCompareDxf('p1', '"abc"')

    expect(result).toEqual({ notModified: true, bytes: null, etag: '"abc"' })
    const call = engine.engineFetch.mock.calls[0] as [string, RequestInit]
    expect(call[1].headers).toEqual({ 'If-None-Match': '"abc"' })
  })

  it('getCompareDxf throws on a real error status', async () => {
    engine.engineFetch.mockResolvedValueOnce(new Response('nope', { status: 409 }))

    await expect(getCompareDxf('p1')).rejects.toMatchObject({ status: 409 })
  })
})
