import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { useCompareStore } from '../../state/compare'
import type { CompareSetSummary, EngineJobSummary, ZwcadStatus } from './api'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/** Indexes an array with a thrown (not `!`-asserted) error on a miss --
 * `@typescript-eslint/no-non-null-assertion` forbids `arr[i]!`. */
function nth<T>(items: T[], index: number): T {
  const item = items[index]
  if (item === undefined) throw new Error(`expected an element at index ${String(index)}`)
  return item
}

const api = vi.hoisted(() => ({
  createSet: vi.fn(),
  getSet: vi.fn(),
  getSetFiles: vi.fn(),
  getZwcadStatus: vi.fn(),
  startFrames: vi.fn(),
  getPairs: vi.fn(),
  pollJob: vi.fn(),
}))

vi.mock('./api', () => ({
  createSet: api.createSet,
  getSet: api.getSet,
  getSetFiles: api.getSetFiles,
  getZwcadStatus: api.getZwcadStatus,
  startFrames: api.startFrames,
  getPairs: api.getPairs,
  createManualPair: vi.fn(),
  deletePair: vi.fn(),
  startRun: vi.fn(),
  pollJob: api.pollJob,
}))

const ipc = vi.hoisted(() => ({ pickFolder: vi.fn() }))
vi.mock('./ipc', () => ({ pickFolder: ipc.pickFolder, copyToClipboard: vi.fn(), openInOS: vi.fn() }))

const { SetScreen } = await import('./SetScreen')

function zwcadFixture(overrides: Partial<ZwcadStatus> = {}): ZwcadStatus {
  return { available: true, installed: true, version: '2026', prog_id: 'ZWCAD.Application', reason: null, ...overrides }
}

function summaryFixture(overrides: Partial<CompareSetSummary> = {}): CompareSetSummary {
  return {
    id: 'cs1',
    project_id: 'p1',
    project_dir: '/project',
    status: 'ingested',
    run_date: '2026-09-04',
    before: { set_id: 'b1', dir: '/before', label: 'before', files: 3, converted: 2, failed: 1, excluded: 0 },
    after: { set_id: 'a1', dir: '/after', label: 'after', files: 3, converted: 3, failed: 0, excluded: 0 },
    converter: { before: 'zwcad-com', after: 'zwcad-com', mismatch_files: 0 },
    zwcad: zwcadFixture(),
    fonts_missing: [],
    crosscheck: null,
    frames: null,
    pairs: null,
    last_job_id: 'job1',
    ...overrides,
  }
}

function jobFixture(overrides: Partial<EngineJobSummary> = {}): EngineJobSummary {
  return {
    id: 'job1',
    status: 'DONE',
    progress: 1,
    message: null,
    compare_set_id: 'cs1',
    kind: 'compare.ingest',
    stage: null,
    ...overrides,
  }
}

function mockPollJobOnce(finalJob: EngineJobSummary): void {
  api.pollJob.mockImplementationOnce(() => ({ promise: Promise.resolve(finalJob), cancel: vi.fn() }))
}

describe('SetScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCompareStore.setState(useCompareStore.getInitialState(), true)
    api.getZwcadStatus.mockResolvedValue(zwcadFixture())
  })

  afterEach(() => {
    cleanup()
  })

  it('renders both folder panels with the empty placeholder and a disabled start button', async () => {
    render(<SetScreen />)

    expect(screen.getAllByText('폴더를 선택하세요')).toHaveLength(2)
    expect(screen.getByRole('button', { name: '인입 시작' })).toBeDisabled()

    await waitFor(() => {
      expect(api.getZwcadStatus).toHaveBeenCalled()
    })
  })

  it('shows the ZWCAD chip once the status loads', async () => {
    render(<SetScreen />)

    await waitFor(() => {
      expect(screen.getByText('ZWCAD 변환')).toBeInTheDocument()
    })
  })

  it('shows the builtin-converter reason when ZWCAD is unavailable', async () => {
    api.getZwcadStatus.mockResolvedValue(zwcadFixture({ available: false, reason: 'not_windows' }))
    render(<SetScreen />)

    await waitFor(() => {
      expect(screen.getByText(/자체 변환기/)).toBeInTheDocument()
      expect(screen.getByText(/Windows 아님/)).toBeInTheDocument()
    })
  })

  it('picking both folders enables 인입 시작, and clicking it drives ingest → frames → the summary card', async () => {
    ipc.pickFolder.mockResolvedValueOnce('/before-dir').mockResolvedValueOnce('/after-dir')
    api.createSet.mockResolvedValueOnce({ compareSetId: 'cs1', projectId: 'p1', jobId: 'ingest-job' })
    api.getSet.mockResolvedValue(summaryFixture())
    api.getSetFiles.mockResolvedValue([
      { id: 'f1', role: 'before', original_name: 'A-101.dwg', import_status: 'FAILED', converter: null, excluded_reason: null, error_message: 'zwcad timeout' },
    ])
    mockPollJobOnce(jobFixture({ id: 'ingest-job', status: 'DONE' }))
    api.startFrames.mockResolvedValueOnce({ jobId: 'frames-job' })
    mockPollJobOnce(jobFixture({ id: 'frames-job', status: 'DONE', kind: 'compare.frames' }))
    api.getPairs.mockResolvedValueOnce([])

    render(<SetScreen />)

    fireEvent.click(nth(screen.getAllByRole('button', { name: '폴더 선택…' }), 0))
    await waitFor(() => {
      expect(screen.getByText('/before-dir')).toBeInTheDocument()
    })
    fireEvent.click(nth(screen.getAllByRole('button', { name: '폴더 선택…' }), 1))
    await waitFor(() => {
      expect(screen.getByText('/after-dir')).toBeInTheDocument()
    })

    const startButton = screen.getByRole('button', { name: '인입 시작' })
    expect(startButton).not.toBeDisabled()
    fireEvent.click(startButton)

    // Wait for the whole chain (ingest job -> frames job -> screen B) to
    // settle before asserting on the summary card -- SetScreen itself stays
    // mounted here (this test renders it directly, not through CompareApp's
    // screen switch), so its data is still on screen after the transition.
    await waitFor(() => {
      expect(useCompareStore.getState().screen).toBe('sheets')
    })
    expect(screen.getAllByText('파일 3개')).toHaveLength(2)
    expect(screen.getByText('실패한 파일')).toBeInTheDocument()
    expect(screen.getByText(/A-101\.dwg/)).toBeInTheDocument()
  })

  it('shows the "준비 중" toast when POST .../frames 404s', async () => {
    ipc.pickFolder.mockResolvedValueOnce('/before-dir').mockResolvedValueOnce('/after-dir')
    api.createSet.mockResolvedValueOnce({ compareSetId: 'cs1', projectId: 'p1', jobId: 'ingest-job' })
    api.getSet.mockResolvedValue(summaryFixture())
    api.getSetFiles.mockResolvedValue([])
    mockPollJobOnce(jobFixture({ id: 'ingest-job', status: 'DONE' }))
    api.startFrames.mockResolvedValueOnce(null)

    render(<SetScreen />)
    fireEvent.click(nth(screen.getAllByRole('button', { name: '폴더 선택…' }), 0))
    fireEvent.click(nth(screen.getAllByRole('button', { name: '폴더 선택…' }), 1))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: '인입 시작' })).not.toBeDisabled()
    })

    fireEvent.click(screen.getByRole('button', { name: '인입 시작' }))

    await waitFor(() => {
      expect(screen.getByText('도곽 추출 기능이 아직 준비되지 않았습니다')).toBeInTheDocument()
    })
    expect(useCompareStore.getState().screen).toBe('set')
  })
})
