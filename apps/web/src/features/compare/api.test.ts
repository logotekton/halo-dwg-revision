import { describe, expect, it, vi } from 'vitest'

const engineFetch = vi.hoisted(() => vi.fn())
vi.mock('../../api/engine', () => ({ engineFetch }))

const {
  createSet,
  EngineHttpError,
  getPairs,
  getZwcadStatus,
  pollJob,
  startFrames,
  startRun,
} = await import('./api')

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  } as unknown as Response
}

describe('createSet', () => {
  it('POSTs snake_case fields and maps the response to camelCase', async () => {
    engineFetch.mockResolvedValueOnce(
      jsonResponse({ compare_set_id: 'cs1', project_id: 'p1', job_id: 'job1' }, 202),
    )

    const result = await createSet({ beforeDir: '/before', afterDir: '/after', runDate: '2026-09-04' })

    expect(result).toEqual({ compareSetId: 'cs1', projectId: 'p1', jobId: 'job1' })
    const [path, init] = engineFetch.mock.calls[0] as [string, RequestInit]
    expect(path).toBe('/api/v1/compare/sets')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      before_dir: '/before',
      after_dir: '/after',
      run_date: '2026-09-04',
      project_dir: undefined,
    })
  })
})

describe('getZwcadStatus', () => {
  it('GETs the zwcad status endpoint', async () => {
    const status = { available: false, installed: false, version: null, prog_id: null, reason: 'not_windows' }
    engineFetch.mockResolvedValueOnce(jsonResponse(status))

    await expect(getZwcadStatus()).resolves.toEqual(status)
    expect(engineFetch).toHaveBeenCalledWith('/api/v1/compare/zwcad/status', {})
  })
})

describe('endpoints not merged yet (R1-04/R1-06)', () => {
  it('startFrames returns null on 404 instead of throwing', async () => {
    engineFetch.mockResolvedValueOnce(jsonResponse({ detail: 'not found' }, 404))

    await expect(startFrames('cs1')).resolves.toBeNull()
  })

  it('startRun returns null on 404 instead of throwing', async () => {
    engineFetch.mockResolvedValueOnce(jsonResponse({ detail: 'not found' }, 404))

    await expect(startRun('cs1')).resolves.toBeNull()
  })

  it('getPairs returns null on 404 instead of throwing', async () => {
    engineFetch.mockResolvedValueOnce(jsonResponse({ detail: 'not found' }, 404))

    await expect(getPairs('cs1')).resolves.toBeNull()
  })

  it('a non-404 error still throws EngineHttpError', async () => {
    engineFetch.mockResolvedValueOnce(jsonResponse({ detail: 'boom' }, 500))

    await expect(startRun('cs1')).rejects.toBeInstanceOf(EngineHttpError)
  })
})

describe('pollJob', () => {
  it('polls until a terminal status, calling onUpdate on every poll', async () => {
    engineFetch
      .mockResolvedValueOnce(jsonResponse({ id: 'j1', status: 'RUNNING', progress: 0.3, message: 'm1', compare_set_id: 'cs1', kind: 'compare.ingest', stage: 'convert' }))
      .mockResolvedValueOnce(jsonResponse({ id: 'j1', status: 'DONE', progress: 1, message: 'done', compare_set_id: 'cs1', kind: 'compare.ingest', stage: null }))

    const updates: number[] = []
    const { promise } = pollJob('j1', (job) => updates.push(job.progress), { intervalMs: 1 })
    const final = await promise

    expect(final.status).toBe('DONE')
    expect(updates).toEqual([0.3, 1])
  })

  it('cancel() stops the loop from firing further onUpdate calls', async () => {
    engineFetch.mockResolvedValue(
      jsonResponse({ id: 'j1', status: 'RUNNING', progress: 0, message: null, compare_set_id: 'cs1', kind: 'compare.ingest', stage: null }),
    )

    const updates: number[] = []
    const { cancel } = pollJob('j1', (job) => updates.push(job.progress), { intervalMs: 1 })
    await new Promise((resolve) => setTimeout(resolve, 5))
    cancel()
    const callsAtCancel = engineFetch.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 20))

    // No further polls happen once cancelled (allow the in-flight one to land).
    expect(engineFetch.mock.calls.length).toBeLessThanOrEqual(callsAtCancel + 1)
  })
})
