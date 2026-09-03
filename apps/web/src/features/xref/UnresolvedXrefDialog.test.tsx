import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { UnresolvedXrefDialog } from './UnresolvedXrefDialog'
import * as api from './api'
import type { XrefLink } from './api'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof api>('./api')
  return {
    ...actual,
    pickOneFile: vi.fn(),
    resolveFileXref: vi.fn(),
    updateSearchPaths: vi.fn(),
    waitForJob: vi.fn(),
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

const UNRESOLVED: XrefLink[] = [
  { blockName: 'F10_GRID', declaredPath: 'F10_grid.dxf', resolvedPath: null, status: 'UNRESOLVED' },
]

describe('UnresolvedXrefDialog', () => {
  it('lists every unresolved block with its declared path', () => {
    render(
      <UnresolvedXrefDialog
        projectId="proj-1"
        fileId="file-1"
        unresolved={UNRESOLVED}
        onClose={vi.fn()}
        onReimported={vi.fn()}
      />,
    )
    expect(screen.getByText('F10_GRID')).toBeInTheDocument()
    expect(screen.getByText('F10_grid.dxf')).toBeInTheDocument()
  })

  it('close button calls onClose', () => {
    const onClose = vi.fn()
    render(
      <UnresolvedXrefDialog
        projectId="proj-1"
        fileId="file-1"
        unresolved={UNRESOLVED}
        onClose={onClose}
        onReimported={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('닫기'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('adding a folder saves it as a search path, waits for the job, then calls onReimported', async () => {
    vi.mocked(api.updateSearchPaths).mockResolvedValue({ searchPaths: ['/xr'], jobIds: ['job-1'] })
    vi.mocked(api.waitForJob).mockResolvedValue('DONE')
    const onReimported = vi.fn()

    render(
      <UnresolvedXrefDialog
        projectId="proj-1"
        fileId="file-1"
        unresolved={UNRESOLVED}
        onClose={vi.fn()}
        onReimported={onReimported}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('폴더 경로 붙여넣기'), { target: { value: '/xr' } })
    fireEvent.click(screen.getByText('검색 경로 추가'))

    await waitFor(() => {
      expect(onReimported).toHaveBeenCalledTimes(1)
    })
    expect(api.updateSearchPaths).toHaveBeenCalledWith('proj-1', ['/xr'], ['file-1'])
    expect(api.waitForJob).toHaveBeenCalledWith('job-1')
  })

  it('matching a file picks one via the native dialog and resolves that block', async () => {
    vi.mocked(api.pickOneFile).mockResolvedValue('/picked/grid.dxf')
    vi.mocked(api.resolveFileXref).mockResolvedValue({ jobId: 'job-2', fileId: 'file-1' })
    vi.mocked(api.waitForJob).mockResolvedValue('DONE')
    const onReimported = vi.fn()

    render(
      <UnresolvedXrefDialog
        projectId="proj-1"
        fileId="file-1"
        unresolved={UNRESOLVED}
        onClose={vi.fn()}
        onReimported={onReimported}
      />,
    )

    fireEvent.click(screen.getByText('파일 매칭...'))

    await waitFor(() => {
      expect(onReimported).toHaveBeenCalledTimes(1)
    })
    expect(api.resolveFileXref).toHaveBeenCalledWith('file-1', 'F10_GRID', '/picked/grid.dxf')
  })

  it('shows an error message and does not call onReimported when the re-import job fails', async () => {
    vi.mocked(api.updateSearchPaths).mockResolvedValue({ searchPaths: ['/xr'], jobIds: ['job-1'] })
    vi.mocked(api.waitForJob).mockResolvedValue('FAILED')
    const onReimported = vi.fn()

    render(
      <UnresolvedXrefDialog
        projectId="proj-1"
        fileId="file-1"
        unresolved={UNRESOLVED}
        onClose={vi.fn()}
        onReimported={onReimported}
      />,
    )

    fireEvent.change(screen.getByPlaceholderText('폴더 경로 붙여넣기'), { target: { value: '/xr' } })
    fireEvent.click(screen.getByText('검색 경로 추가'))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('재임포트에 실패했습니다')
    })
    expect(onReimported).not.toHaveBeenCalled()
  })
})
