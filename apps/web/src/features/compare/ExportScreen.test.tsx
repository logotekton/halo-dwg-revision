import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { useCompareStore } from '../../state/compare'
import { useExportStore } from '../../state/export'
import type { CompareSetSummary, EngineJobSummary, SheetPair, ZwcadStatus } from './api'
import type { ClustersSidecar } from './reviewApi'
import type { Run } from './exportApi'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const api = vi.hoisted(() => ({ pollJob: vi.fn() }))
vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, pollJob: api.pollJob }
})

const exportApi = vi.hoisted(() => ({
  startExport: vi.fn(),
  getRun: vi.fn(),
  getRunTsv: vi.fn(),
}))
vi.mock('./exportApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./exportApi')>()
  return { ...actual, startExport: exportApi.startExport, getRun: exportApi.getRun, getRunTsv: exportApi.getRunTsv }
})

const reviewApi = vi.hoisted(() => ({ getClusters: vi.fn() }))
vi.mock('./reviewApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./reviewApi')>()
  return { ...actual, getClusters: reviewApi.getClusters }
})

const ipc = vi.hoisted(() => ({ copyToClipboard: vi.fn(), openInOS: vi.fn() }))
vi.mock('./ipc', () => ({ pickFolder: vi.fn(), copyToClipboard: ipc.copyToClipboard, openInOS: ipc.openInOS }))

const { ExportScreen } = await import('./ExportScreen')

function zwcadFixture(overrides: Partial<ZwcadStatus> = {}): ZwcadStatus {
  return { available: true, installed: true, version: '2026', prog_id: 'ZWCAD.Application', reason: null, ...overrides }
}

function summaryFixture(overrides: Partial<CompareSetSummary> = {}): CompareSetSummary {
  return {
    id: 'cs1',
    project_id: 'p1',
    project_dir: '/project',
    status: 'compared',
    run_date: '2026-09-04',
    before: { set_id: 'b1', dir: '/before', label: 'before', files: 1, converted: 1, failed: 0, excluded: 0 },
    after: { set_id: 'a1', dir: '/after', label: 'after', files: 1, converted: 1, failed: 0, excluded: 0 },
    converter: { before: null, after: null, mismatch_files: 0 },
    zwcad: zwcadFixture(),
    fonts_missing: [],
    crosscheck: null,
    frames: { before: 2, after: 2, unrecognized_files: 0 },
    pairs: { changed: 1, same: 1, added: 0, removed: 0, unpaired: 0, unrecognized: 0, converter_mismatch: 0, pending: 0 },
    last_job_id: 'job1',
    ...overrides,
  }
}

function pairFixture(overrides: Partial<SheetPair> = {}): SheetPair {
  return {
    id: 'pair-a102',
    compare_set_id: 'cs1',
    before_frame_id: 'f1',
    after_frame_id: 'f2',
    status: 'changed',
    match_method: 'number',
    sort_key: 'A-102',
    change_count: 2,
    minor_count: 0,
    cluster_count: 2,
    compare_dxf_path: '/cs1/pair-a102/compare.dxf',
    ...overrides,
  }
}

function sidecarFixture(overrides: Partial<ClustersSidecar> = {}): ClustersSidecar {
  return {
    schema_version: '0.1',
    pair_id: 'pair-a102',
    pair_key: 'A-102',
    run_date: '2026-09-04',
    layer: 'REV-20260904',
    frame: { bbox: [0, 0, 100, 100], scale_denominator: 100, scale_factor: 1, offset_before: [0, 0] },
    clusters: [],
    changes: [],
    handle_to_cluster: {},
    counts: { clusters: 2, changes: 2, minor: 0, approved: 1, ignored: 1 },
    ...overrides,
  }
}

function jobFixture(overrides: Partial<EngineJobSummary> = {}): EngineJobSummary {
  return {
    id: 'export-job',
    status: 'DONE',
    progress: 1,
    message: null,
    compare_set_id: 'cs1',
    kind: 'compare.export',
    stage: null,
    ...overrides,
  }
}

function runFixture(overrides: Partial<Run> = {}): Run {
  return {
    id: 'run1',
    compare_set_id: 'cs1',
    run_date: '2026-09-04',
    layer_name: 'REV-20260904',
    output_dir: '/project/출력/2026-09-04',
    scope: 'all',
    method: 'auto',
    pair_ids: ['pair-a102'],
    approved_count: 1,
    ignored_count: 1,
    files: [
      {
        pair_id: 'pair-a102',
        sheet_no: 'A-102',
        path: '/project/출력/2026-09-04/A-102_after_markup.dxf',
        format: 'dxf',
        writer: 'dxf-only',
      },
    ],
    status: 'done',
    created_at: '2026-09-04T00:00:00',
    ...overrides,
  }
}

function mockPollJobOnce(finalJob: EngineJobSummary): void {
  api.pollJob.mockImplementationOnce(() => ({ promise: Promise.resolve(finalJob), cancel: vi.fn() }))
}

describe('ExportScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCompareStore.setState(useCompareStore.getInitialState(), true)
    useExportStore.setState(useExportStore.getInitialState(), true)
    reviewApi.getClusters.mockResolvedValue(sidecarFixture())
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the 전체 도곽 scope and the ZWCAD-available method, and defaults the run date from the set', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', summary: summaryFixture(), pairs: [pairFixture()], zwcad: zwcadFixture() })

    render(<ExportScreen />)

    expect(screen.getByText('전체 도곽')).toBeInTheDocument()
    expect(screen.getByText('DWG(ZWCAD)')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByLabelText('실행 날짜')).toHaveValue('2026-09-04')
    })
  })

  it('shows DXF(ZWCAD 없음) when ZWCAD is unavailable', async () => {
    useCompareStore.setState({
      compareSetId: 'cs1',
      summary: summaryFixture(),
      pairs: [pairFixture()],
      zwcad: zwcadFixture({ available: false, reason: 'not_windows' }),
    })

    render(<ExportScreen />)

    expect(screen.getByText('DXF(ZWCAD 없음)')).toBeInTheDocument()
    // Lets the preview effect's `getClusters` promise settle before the test
    // ends, so the state update it triggers is not left dangling (act warning).
    await waitFor(() => {
      expect(reviewApi.getClusters).toHaveBeenCalled()
    })
  })

  it('sums approved/ignored counts and target sheets from each candidate pair\'s sidecar', async () => {
    useCompareStore.setState({
      compareSetId: 'cs1',
      summary: summaryFixture(),
      pairs: [pairFixture(), pairFixture({ id: 'pair-a101', status: 'same', cluster_count: 0, compare_dxf_path: null })],
    })

    render(<ExportScreen />)

    await waitFor(() => {
      expect(screen.getByText('승인 1건 · 무시 1건 · 대상 도곽 1장')).toBeInTheDocument()
    })
    // Only the one candidate pair (cluster_count > 0 with a compare DXF) is asked for its sidecar.
    expect(reviewApi.getClusters).toHaveBeenCalledTimes(1)
    expect(reviewApi.getClusters).toHaveBeenCalledWith('pair-a102')
  })

  it('출력 실행 runs the export job to completion and renders the result table + output folder', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', summary: summaryFixture(), pairs: [pairFixture()] })
    exportApi.startExport.mockResolvedValueOnce({ jobId: 'export-job', runId: 'run1' })
    mockPollJobOnce(jobFixture({ status: 'DONE' }))
    exportApi.getRun.mockResolvedValueOnce(runFixture())

    render(<ExportScreen />)

    fireEvent.click(screen.getByRole('button', { name: '출력 실행' }))

    await waitFor(() => {
      expect(screen.getByTestId('export-result')).toBeInTheDocument()
    })
    expect(exportApi.startExport).toHaveBeenCalledWith('cs1', { runDate: '2026-09-04' })
    expect(screen.getByText('/project/출력/2026-09-04')).toBeInTheDocument()
    expect(screen.getByText('A-102')).toBeInTheDocument()
    expect(screen.getByText('ZWCAD 없음: DXF로 출력됨')).toBeInTheDocument()
  })

  it('shows the engine error with a retry button when the export job fails', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', summary: summaryFixture(), pairs: [pairFixture()] })
    exportApi.startExport.mockResolvedValueOnce({ jobId: 'export-job', runId: 'run1' })
    mockPollJobOnce(jobFixture({ status: 'FAILED', error: 'markup failed for A-102' }))

    render(<ExportScreen />)
    fireEvent.click(screen.getByRole('button', { name: '출력 실행' }))

    await waitFor(() => {
      expect(screen.getByText('markup failed for A-102')).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
    expect(screen.queryByTestId('export-result')).not.toBeInTheDocument()
  })

  it('폴더 열기 opens the run\'s output_dir and 변경 리스트 TSV 복사 copies the TSV text', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', summary: summaryFixture(), pairs: [pairFixture()] })
    useExportStore.setState({ run: runFixture() })
    exportApi.getRunTsv.mockResolvedValueOnce('도면번호\t도면명\n')

    render(<ExportScreen />)

    fireEvent.click(screen.getByRole('button', { name: '폴더 열기' }))
    await waitFor(() => {
      expect(ipc.openInOS).toHaveBeenCalledWith('/project/출력/2026-09-04')
    })

    fireEvent.click(screen.getByRole('button', { name: '변경 리스트 TSV 복사' }))
    await waitFor(() => {
      expect(ipc.copyToClipboard).toHaveBeenCalledWith('도면번호\t도면명\n')
    })
    await waitFor(() => {
      expect(screen.getByText('TSV를 클립보드에 복사했습니다')).toBeInTheDocument()
    })
  })

  it('목록으로 / 도곽 목록으로 send the store back to screen B', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', summary: summaryFixture(), pairs: [pairFixture()], screen: 'export' })

    render(<ExportScreen />)
    fireEvent.click(screen.getByRole('button', { name: '도곽 목록으로' }))

    expect(useCompareStore.getState().screen).toBe('sheets')
    await waitFor(() => {
      expect(reviewApi.getClusters).toHaveBeenCalled()
    })
  })
})
