import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useFilesFeature } from './useFilesFeature'

const pickDrawingsMock = vi.fn<() => Promise<string[]>>()
// Vitest hoists vi.mock calls above imports, so useFilesFeature's own
// `import { pickDrawings } from './api'` resolves to this mock regardless
// of the source-order above.
vi.mock('./api', () => ({
  pickDrawings: () => pickDrawingsMock(),
}))

describe('useFilesFeature', () => {
  beforeEach(() => {
    window.localStorage.clear()
    pickDrawingsMock.mockReset()
  })

  it('starts with an empty recent list when localStorage has nothing stored', () => {
    const { result } = renderHook(() => useFilesFeature())
    expect(result.current.recent).toEqual([])
  })

  it('restores a previously stored recent list on mount', () => {
    window.localStorage.setItem('halo-cad:recent-files', JSON.stringify(['/a.dwg', '/b.dxf']))
    const { result } = renderHook(() => useFilesFeature())
    expect(result.current.recent).toEqual(['/a.dwg', '/b.dxf'])
  })

  it('ignores corrupted localStorage content instead of throwing', () => {
    window.localStorage.setItem('halo-cad:recent-files', '{not json')
    const { result } = renderHook(() => useFilesFeature())
    expect(result.current.recent).toEqual([])
  })

  it('openFiles() calls pickDrawings() and prepends the result to recent', async () => {
    pickDrawingsMock.mockResolvedValue(['/a.dwg'])
    const { result } = renderHook(() => useFilesFeature())

    await act(async () => {
      await result.current.openFiles()
    })

    expect(pickDrawingsMock).toHaveBeenCalledTimes(1)
    expect(result.current.recent).toEqual(['/a.dwg'])
    expect(JSON.parse(window.localStorage.getItem('halo-cad:recent-files') ?? '[]')).toEqual(['/a.dwg'])
  })

  it('openFiles() with an empty pick (dialog cancelled) leaves recent untouched', async () => {
    pickDrawingsMock.mockResolvedValue([])
    const { result } = renderHook(() => useFilesFeature())

    await act(async () => {
      await result.current.openFiles()
    })

    expect(result.current.recent).toEqual([])
  })

  it('opening an already-recent path moves it back to the front instead of duplicating', async () => {
    pickDrawingsMock.mockResolvedValueOnce(['/a.dwg', '/b.dwg']).mockResolvedValueOnce(['/a.dwg'])
    const { result } = renderHook(() => useFilesFeature())

    await act(async () => {
      await result.current.openFiles()
    })
    await act(async () => {
      await result.current.openFiles()
    })

    expect(result.current.recent).toEqual(['/a.dwg', '/b.dwg'])
  })

  it('caps the recent list at 10 entries, dropping the oldest', async () => {
    const { result } = renderHook(() => useFilesFeature())
    for (let i = 0; i < 12; i += 1) {
      pickDrawingsMock.mockResolvedValueOnce([`/file-${String(i)}.dwg`])
      // Sequential opens must observe each other's recent-list update.
      await act(async () => {
        await result.current.openFiles()
      })
    }

    expect(result.current.recent).toHaveLength(10)
    expect(result.current.recent[0]).toBe('/file-11.dwg')
  })

  it('openRecent() re-adds the path to the front of recent', () => {
    const { result } = renderHook(() => useFilesFeature())

    act(() => {
      result.current.openRecent('/again.dwg')
    })

    expect(result.current.recent).toEqual(['/again.dwg'])
  })
})
