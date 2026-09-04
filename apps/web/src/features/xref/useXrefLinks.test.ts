import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useXrefLinks } from './useXrefLinks'
import * as api from './api'

vi.mock('./api', () => ({ getFileXrefs: vi.fn() }))

afterEach(() => {
  vi.clearAllMocks()
})

describe('useXrefLinks', () => {
  it('returns an empty, non-loading result when fileId is null, without fetching', () => {
    const { result } = renderHook(() => useXrefLinks(null))
    expect(result.current).toEqual({ links: [], loading: false, error: null, refetch: expect.any(Function) })
    expect(api.getFileXrefs).not.toHaveBeenCalled()
  })

  it('fetches xrefs for a given fileId and resolves to loading:false with the links', async () => {
    vi.mocked(api.getFileXrefs).mockResolvedValue([
      { blockName: 'F10_GRID', declaredPath: 'F10_grid.dxf', resolvedPath: '/x', status: 'RESOLVED' },
    ])

    const { result } = renderHook(() => useXrefLinks('file-1'))
    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.links).toHaveLength(1)
    expect(result.current.error).toBeNull()
    expect(api.getFileXrefs).toHaveBeenCalledWith('file-1')
  })

  it('surfaces a fetch failure as `error`, with an empty link list', async () => {
    vi.mocked(api.getFileXrefs).mockRejectedValue(new Error('boom'))

    const { result } = renderHook(() => useXrefLinks('file-1'))
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(result.current.error).toBe('boom')
    expect(result.current.links).toEqual([])
  })

  it('refetch() re-runs the fetch', async () => {
    vi.mocked(api.getFileXrefs).mockResolvedValue([])
    const { result } = renderHook(() => useXrefLinks('file-1'))
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })
    expect(api.getFileXrefs).toHaveBeenCalledTimes(1)

    act(() => {
      result.current.refetch()
    })
    await waitFor(() => {
      expect(api.getFileXrefs).toHaveBeenCalledTimes(2)
    })
  })

  it('re-fetches when fileId changes', async () => {
    vi.mocked(api.getFileXrefs).mockResolvedValue([])
    const { result, rerender } = renderHook(({ fileId }: { fileId: string | null }) => useXrefLinks(fileId), {
      initialProps: { fileId: 'file-1' },
    })
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    rerender({ fileId: 'file-2' })
    await waitFor(() => {
      expect(api.getFileXrefs).toHaveBeenLastCalledWith('file-2')
    })
  })
})
