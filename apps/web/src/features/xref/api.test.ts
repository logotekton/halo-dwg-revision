import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EngineConnection } from '../../api/types'

function mockHalocad(pickDrawings: () => Promise<string[]> = vi.fn().mockResolvedValue([])): void {
  const connection: EngineConnection = { baseUrl: 'http://127.0.0.1:54213', token: 'tok' }
  Object.defineProperty(window, 'halocad', {
    configurable: true,
    value: {
      files: { pickDrawings },
      app: { getVersion: vi.fn(), platform: 'darwin' },
      engine: { getConnection: vi.fn().mockResolvedValue(connection), onStatus: vi.fn(() => () => undefined) },
    },
  })
}

describe('features/xref/api', () => {
  beforeEach(() => {
    vi.resetModules()
    mockHalocad()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('getFileXrefs converts the snake_case DTO to camelCase', async () => {
    const body = [
      { block_name: 'F10_GRID', declared_path: 'F10_grid.dxf', resolved_path: '/x/F10_grid.dxf', status: 'RESOLVED' },
      { block_name: 'PLAN', declared_path: '..\\XR\\PLAN.dwg', resolved_path: null, status: 'UNRESOLVED' },
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })))

    const { getFileXrefs } = await import('./api')
    const links = await getFileXrefs('file-1')

    expect(links).toEqual([
      { blockName: 'F10_GRID', declaredPath: 'F10_grid.dxf', resolvedPath: '/x/F10_grid.dxf', status: 'RESOLVED' },
      { blockName: 'PLAN', declaredPath: '..\\XR\\PLAN.dwg', resolvedPath: null, status: 'UNRESOLVED' },
    ])
  })

  it('getFileXrefs throws with the response status on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('not found', { status: 404 })))

    const { getFileXrefs } = await import('./api')
    await expect(getFileXrefs('missing')).rejects.toThrow('404')
  })

  it('resolveFileXref posts resolved_path and returns {jobId, fileId}', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ job_id: 'job-1', file_id: 'file-1' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { resolveFileXref } = await import('./api')
    const result = await resolveFileXref('file-1', 'F10_GRID', '/picked/grid.dxf')

    expect(result).toEqual({ jobId: 'job-1', fileId: 'file-1' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/files/file-1/xrefs/F10_GRID/resolve')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ resolved_path: '/picked/grid.dxf' })
  })

  it('updateSearchPaths puts search_paths + reimport_file_ids and returns job ids', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ search_paths: ['/xr'], job_ids: ['job-1'] }), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    const { updateSearchPaths } = await import('./api')
    const result = await updateSearchPaths('proj-1', ['/xr'], ['file-1'])

    expect(result).toEqual({ searchPaths: ['/xr'], jobIds: ['job-1'] })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/projects/proj-1/search-paths')
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({
      search_paths: ['/xr'],
      reimport_file_ids: ['file-1'],
    })
  })

  it('getImportSettings / updateImportSettings round-trip camelCase <-> snake_case', async () => {
    const fetchMock = vi.fn().mockImplementation(
      () =>
        new Response(JSON.stringify({ search_paths: ['/a'], ignore_patterns: ['*.bak'] }), {
          status: 200,
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const { getImportSettings, updateImportSettings } = await import('./api')
    expect(await getImportSettings('proj-1')).toEqual({ searchPaths: ['/a'], ignorePatterns: ['*.bak'] })

    await updateImportSettings('proj-1', { searchPaths: ['/a'], ignorePatterns: ['*.bak'] })
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ search_paths: ['/a'], ignore_patterns: ['*.bak'] })
  })

  it('waitForJob polls getJobStatus until a terminal status', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'RUNNING' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'DONE' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const { waitForJob } = await import('./api')
    const status = await waitForJob('job-1', 5_000)

    expect(status).toBe('DONE')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('pickOneFile returns the first picked path, or null when cancelled', async () => {
    mockHalocad(vi.fn().mockResolvedValue(['/a.dwg', '/b.dwg']))
    const { pickOneFile } = await import('./api')
    expect(await pickOneFile()).toBe('/a.dwg')

    mockHalocad(vi.fn().mockResolvedValue([]))
    const { pickOneFile: pickOneFile2 } = await import('./api')
    expect(await pickOneFile2()).toBeNull()
  })
})
