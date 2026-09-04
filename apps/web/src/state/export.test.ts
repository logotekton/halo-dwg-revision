import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { EngineJobSummary } from '../features/compare/api'
import type { Run } from '../features/compare/exportApi'

// `pollJob` is the seam mocked here (not `getJob`), exactly like
// `state/compare.test.ts`: `state/export.ts` only ever reaches the engine's
// job endpoint through it, so replacing this one cross-module import fully
// controls every test's job lifecycle without waiting on the real 500ms poll.
const api = vi.hoisted(() => ({ pollJob: vi.fn() }))
vi.mock('../features/compare/api', () => ({ pollJob: api.pollJob }))

const exportApi = vi.hoisted(() => ({
  startExport: vi.fn(),
  getRun: vi.fn(),
  getRunTsv: vi.fn(),
}))
vi.mock('../features/compare/exportApi', () => ({
  startExport: exportApi.startExport,
  getRun: exportApi.getRun,
  getRunTsv: exportApi.getRunTsv,
}))

const ipc = vi.hoisted(() => ({ copyToClipboard: vi.fn(), openInOS: vi.fn() }))
vi.mock('../features/compare/ipc', () => ({
  pickFolder: vi.fn(),
  copyToClipboard: ipc.copyToClipboard,
  openInOS: ipc.openInOS,
}))

const { useExportStore } = await import('./export')

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
    pair_ids: ['pair1'],
    approved_count: 1,
    ignored_count: 1,
    files: [{ pair_id: 'pair1', sheet_no: 'A-102', path: '/project/출력/2026-09-04/A-102_after_markup.dxf', format: 'dxf', writer: 'dxf-only' }],
    status: 'done',
    created_at: '2026-09-04T00:00:00',
    ...overrides,
  }
}

/** Queues one `pollJob` call: fires `updates` through `onUpdate` (in order)
 * then resolves with `finalJob` -- same helper `state/compare.test.ts` uses. */
function mockPollJobOnce(finalJob: EngineJobSummary, updates: EngineJobSummary[] = []): void {
  api.pollJob.mockImplementationOnce((_jobId: string, onUpdate: (job: EngineJobSummary) => void) => {
    for (const update of updates) onUpdate(update)
    return { promise: Promise.resolve(finalJob), cancel: vi.fn() }
  })
}

describe('export store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useExportStore.setState(useExportStore.getInitialState(), true)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts empty', () => {
    const state = useExportStore.getState()
    expect(state.runDate).toBe('')
    expect(state.run).toBeNull()
    expect(state.exportJob).toBeNull()
    expect(state.busy).toBe(false)
  })

  it('setRunDate only changes the run-date field', () => {
    useExportStore.getState().setRunDate('2026-09-05')
    expect(useExportStore.getState().runDate).toBe('2026-09-05')
  })

  it('runExport drives the job to completion and stores the finished Run', async () => {
    exportApi.startExport.mockResolvedValueOnce({ jobId: 'export-job', runId: 'run1' })
    mockPollJobOnce(jobFixture({ status: 'DONE' }), [jobFixture({ status: 'RUNNING', progress: 0.5, stage: 'markup' })])
    exportApi.getRun.mockResolvedValueOnce(runFixture())

    await useExportStore.getState().runExport({ compareSetId: 'cs1', runDate: '2026-09-04' })

    expect(exportApi.startExport).toHaveBeenCalledWith('cs1', { runDate: '2026-09-04' })
    expect(exportApi.getRun).toHaveBeenCalledWith('run1')
    expect(useExportStore.getState().run).toEqual(runFixture())
    expect(useExportStore.getState().exportJob).toBeNull()
    expect(useExportStore.getState().busy).toBe(false)
    expect(useExportStore.getState().error).toBeNull()
  })

  it('reports progress from the job poll before it settles', async () => {
    exportApi.startExport.mockResolvedValueOnce({ jobId: 'export-job', runId: 'run1' })
    let capturedStage: string | null = null
    api.pollJob.mockImplementationOnce((_jobId: string, onUpdate: (job: EngineJobSummary) => void) => {
      onUpdate(jobFixture({ status: 'RUNNING', progress: 0.5, stage: 'dwg' }))
      capturedStage = useExportStore.getState().exportJob?.stage ?? null
      return { promise: Promise.resolve(jobFixture({ status: 'DONE' })), cancel: vi.fn() }
    })
    exportApi.getRun.mockResolvedValueOnce(runFixture())

    await useExportStore.getState().runExport({ compareSetId: 'cs1', runDate: '2026-09-04' })

    expect(capturedStage).toBe('dwg')
  })

  it('surfaces the job error and leaves run untouched when the job fails', async () => {
    exportApi.startExport.mockResolvedValueOnce({ jobId: 'export-job', runId: 'run1' })
    mockPollJobOnce(jobFixture({ status: 'FAILED', error: 'markup failed for A-102' }))

    await useExportStore.getState().runExport({ compareSetId: 'cs1', runDate: '2026-09-04' })

    expect(useExportStore.getState().error).toBe('markup failed for A-102')
    expect(useExportStore.getState().run).toBeNull()
    expect(useExportStore.getState().busy).toBe(false)
    expect(exportApi.getRun).not.toHaveBeenCalled()
  })

  it('surfaces a 409 from POST .../export (compare_set not "compared") as an error', async () => {
    exportApi.startExport.mockRejectedValueOnce(new Error('/api/v1/compare/sets/cs1/export failed (409): not compared'))

    await useExportStore.getState().runExport({ compareSetId: 'cs1', runDate: '2026-09-04' })

    expect(useExportStore.getState().error).toMatch(/409/)
    expect(useExportStore.getState().busy).toBe(false)
  })

  it('copyTsv is a no-op before a run exists', async () => {
    await useExportStore.getState().copyTsv()
    expect(exportApi.getRunTsv).not.toHaveBeenCalled()
    expect(ipc.copyToClipboard).not.toHaveBeenCalled()
  })

  it('copyTsv fetches the TSV, writes it to the clipboard and shows a toast that clears itself after 2s', async () => {
    vi.useFakeTimers()
    useExportStore.setState({ run: runFixture() })
    exportApi.getRunTsv.mockResolvedValueOnce('도면번호\t도면명\n')

    await useExportStore.getState().copyTsv()

    expect(exportApi.getRunTsv).toHaveBeenCalledWith('run1')
    expect(ipc.copyToClipboard).toHaveBeenCalledWith('도면번호\t도면명\n')
    expect(useExportStore.getState().toast).toBe('compare.export.toast.tsvCopied')

    await vi.advanceTimersByTimeAsync(2_000)
    expect(useExportStore.getState().toast).toBeNull()
  })

  it('copyTsv surfaces a failure instead of the toast', async () => {
    useExportStore.setState({ run: runFixture() })
    exportApi.getRunTsv.mockRejectedValueOnce(new Error('tsv not written yet'))

    await useExportStore.getState().copyTsv()

    expect(useExportStore.getState().error).toBe('tsv not written yet')
    expect(useExportStore.getState().toast).toBeNull()
  })

  it('openOutput is a no-op before a run exists, and opens the run\'s output_dir once one does', async () => {
    await useExportStore.getState().openOutput()
    expect(ipc.openInOS).not.toHaveBeenCalled()

    useExportStore.setState({ run: runFixture() })
    await useExportStore.getState().openOutput()
    expect(ipc.openInOS).toHaveBeenCalledWith('/project/출력/2026-09-04')
  })

  it('reset clears the run, job and error back to the initial state', () => {
    useExportStore.setState({ run: runFixture(), error: 'boom', runDate: '2026-09-04', toast: 'compare.export.toast.tsvCopied' })
    useExportStore.getState().reset()

    const state = useExportStore.getState()
    expect(state.run).toBeNull()
    expect(state.error).toBeNull()
    expect(state.runDate).toBe('')
    expect(state.toast).toBeNull()
  })
})
