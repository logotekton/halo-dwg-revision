import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompareSetSummary, EngineJobSummary, SheetPair, ZwcadStatus } from '../features/compare/api'

// `pollJob` (not `getJob`) is the seam mocked here, not `getJob` itself:
// `state/compare.ts` only ever reaches the engine's job endpoint through
// `pollJob`, so replacing that one cross-module import fully controls every
// test's job lifecycle without needing fake timers for `pollJob`'s real
// 500ms poll interval.
const api = vi.hoisted(() => ({
  createSet: vi.fn(),
  getSet: vi.fn(),
  getSetFiles: vi.fn(),
  getZwcadStatus: vi.fn(),
  startFrames: vi.fn(),
  getPairs: vi.fn(),
  createManualPair: vi.fn(),
  deletePair: vi.fn(),
  startRun: vi.fn(),
  pollJob: vi.fn(),
}))

vi.mock('../features/compare/api', () => ({
  createSet: api.createSet,
  getSet: api.getSet,
  getSetFiles: api.getSetFiles,
  getZwcadStatus: api.getZwcadStatus,
  startFrames: api.startFrames,
  getPairs: api.getPairs,
  createManualPair: api.createManualPair,
  deletePair: api.deletePair,
  startRun: api.startRun,
  pollJob: api.pollJob,
}))

const ipc = vi.hoisted(() => ({ pickFolder: vi.fn() }))
vi.mock('../features/compare/ipc', () => ({
  pickFolder: ipc.pickFolder,
  copyToClipboard: vi.fn(),
  openInOS: vi.fn(),
}))

const { useCompareStore } = await import('./compare')

function summaryFixture(overrides: Partial<CompareSetSummary> = {}): CompareSetSummary {
  return {
    id: 'cs1',
    project_id: 'p1',
    project_dir: '/project',
    status: 'ingested',
    run_date: '2026-09-04',
    before: { set_id: 'b1', dir: '/before', label: 'before', files: 2, converted: 2, failed: 0, excluded: 0 },
    after: { set_id: 'a1', dir: '/after', label: 'after', files: 2, converted: 2, failed: 0, excluded: 0 },
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

function zwcadFixture(): ZwcadStatus {
  return { available: true, installed: true, version: '2026', prog_id: 'ZWCAD.Application', reason: null }
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

function pairFixture(overrides: Partial<SheetPair> = {}): SheetPair {
  return {
    id: 'pair1',
    compare_set_id: 'cs1',
    before_frame_id: 'f1',
    after_frame_id: 'f2',
    status: 'changed',
    match_method: 'number',
    score: 1,
    sort_key: 'A-101',
    change_count: 3,
    minor_count: 0,
    cluster_count: 2,
    compare_dxf_path: null,
    clusters_json_path: null,
    warnings: null,
    ...overrides,
  }
}

/** Queues one `pollJob` call: fires `updates` through `onUpdate` (in order)
 * then resolves with `finalJob`, all synchronously-ish (no real 500ms
 * sleep, unlike the real `pollJob`). */
function mockPollJobOnce(finalJob: EngineJobSummary, updates: EngineJobSummary[] = []): void {
  api.pollJob.mockImplementationOnce((_jobId: string, onUpdate: (job: EngineJobSummary) => void) => {
    for (const update of updates) onUpdate(update)
    return { promise: Promise.resolve(finalJob), cancel: vi.fn() }
  })
}

describe('compare store', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCompareStore.setState(useCompareStore.getInitialState(), true)
  })

  it('starts on the set screen with today as the default run date', () => {
    const state = useCompareStore.getState()
    expect(state.screen).toBe('set')
    expect(state.runDate).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('goto switches the current screen and nothing else', () => {
    useCompareStore.getState().goto('sheets')
    expect(useCompareStore.getState().screen).toBe('sheets')
  })

  it('pickBefore/pickAfter set the folder only when the dialog resolves a path', async () => {
    ipc.pickFolder.mockResolvedValueOnce('/picked/before')
    await useCompareStore.getState().pickBefore()
    expect(useCompareStore.getState().beforeDir).toBe('/picked/before')

    ipc.pickFolder.mockResolvedValueOnce(null)
    await useCompareStore.getState().pickAfter()
    expect(useCompareStore.getState().afterDir).toBeNull()
  })

  it('startSet runs ingest to completion, then frames, then lands on the sheets screen', async () => {
    useCompareStore.setState({ beforeDir: '/before', afterDir: '/after', runDate: '2026-09-04' })
    api.createSet.mockResolvedValueOnce({ compareSetId: 'cs1', projectId: 'p1', jobId: 'ingest-job' })
    api.getSet.mockResolvedValue(summaryFixture())
    api.getSetFiles.mockResolvedValue([])
    mockPollJobOnce(jobFixture({ id: 'ingest-job', status: 'DONE' }), [
      jobFixture({ id: 'ingest-job', status: 'RUNNING', progress: 0.5, stage: 'convert' }),
    ])
    api.startFrames.mockResolvedValueOnce({ jobId: 'frames-job' })
    mockPollJobOnce(jobFixture({ id: 'frames-job', status: 'DONE', kind: 'compare.frames' }))
    api.getPairs.mockResolvedValueOnce([pairFixture()])

    await useCompareStore.getState().startSet()

    expect(api.createSet).toHaveBeenCalledWith({ beforeDir: '/before', afterDir: '/after', runDate: '2026-09-04' })
    expect(api.startFrames).toHaveBeenCalledWith('cs1')
    expect(useCompareStore.getState().screen).toBe('sheets')
    expect(useCompareStore.getState().pairs).toEqual([pairFixture()])
    expect(useCompareStore.getState().pairsAvailable).toBe(true)
    expect(useCompareStore.getState().job).toBeNull()
    expect(useCompareStore.getState().busy).toBe(false)
  })

  it('stops and surfaces an error when the ingest job itself fails', async () => {
    useCompareStore.setState({ beforeDir: '/before', afterDir: '/after' })
    api.createSet.mockResolvedValueOnce({ compareSetId: 'cs1', projectId: 'p1', jobId: 'ingest-job' })
    api.getSet.mockResolvedValue(summaryFixture({ status: 'failed' }))
    api.getSetFiles.mockResolvedValue([])
    mockPollJobOnce(jobFixture({ id: 'ingest-job', status: 'FAILED', error: 'all files failed to convert' }))

    await useCompareStore.getState().startSet()

    expect(api.startFrames).not.toHaveBeenCalled()
    expect(useCompareStore.getState().error).toBe('all files failed to convert')
    expect(useCompareStore.getState().screen).toBe('set')
  })

  it('shows the "준비 중" toast and stays put when POST .../frames 404s (R1-04 not merged)', async () => {
    useCompareStore.setState({ beforeDir: '/before', afterDir: '/after', compareSetId: 'cs1' })
    api.startFrames.mockResolvedValueOnce(null)

    await useCompareStore.getState().startFrames()

    expect(useCompareStore.getState().screen).toBe('set')
    expect(useCompareStore.getState().toast).toBe('compare.set.toast.framesNotReady')
    expect(useCompareStore.getState().busy).toBe(false)
  })

  it('shows the "준비 중" toast and keeps state when POST .../run 404s (R1-06 not merged)', async () => {
    useCompareStore.setState({ compareSetId: 'cs1' })
    api.startRun.mockResolvedValueOnce(null)

    await useCompareStore.getState().startRun()

    expect(useCompareStore.getState().toast).toBe('compare.sheets.toast.runNotReady')
    expect(useCompareStore.getState().hasRunCompare).toBe(false)
  })

  it('startRun success flips hasRunCompare and reloads pairs + summary', async () => {
    useCompareStore.setState({ compareSetId: 'cs1' })
    api.startRun.mockResolvedValueOnce({ jobId: 'run-job' })
    mockPollJobOnce(jobFixture({ id: 'run-job', status: 'DONE', kind: 'compare.run' }))
    api.getPairs.mockResolvedValueOnce([pairFixture({ status: 'same', change_count: 0 })])
    api.getSet.mockResolvedValueOnce(summaryFixture({ status: 'compared' }))
    api.getSetFiles.mockResolvedValueOnce([])

    await useCompareStore.getState().startRun()

    expect(useCompareStore.getState().hasRunCompare).toBe(true)
    expect(useCompareStore.getState().pairs[0]?.status).toBe('same')
  })

  it('loadPairs marks pairsAvailable false without inventing rows when the endpoint 404s', async () => {
    useCompareStore.setState({ compareSetId: 'cs1' })
    api.getPairs.mockResolvedValueOnce(null)

    await useCompareStore.getState().loadPairs()

    expect(useCompareStore.getState().pairsAvailable).toBe(false)
    expect(useCompareStore.getState().pairs).toEqual([])
  })

  it('setFilters merges instead of replacing the filter object', () => {
    useCompareStore.getState().setFilters({ q: 'A-101' })
    useCompareStore.getState().setFilters({ status: 'changed' })

    expect(useCompareStore.getState().filters).toEqual({ status: 'changed', q: 'A-101', sort: 'sort_key' })
  })

  it('openPair selects the pair and moves to the review screen', () => {
    useCompareStore.getState().openPair('pair1')

    expect(useCompareStore.getState().selectedPairId).toBe('pair1')
    expect(useCompareStore.getState().screen).toBe('review')
  })

  it('createManualPair reloads the pair list on success', async () => {
    useCompareStore.setState({ compareSetId: 'cs1' })
    api.createManualPair.mockResolvedValueOnce(pairFixture({ match_method: 'manual' }))
    api.getPairs.mockResolvedValueOnce([pairFixture({ match_method: 'manual' })])

    await useCompareStore.getState().createManualPair('f1', 'f2')

    expect(api.createManualPair).toHaveBeenCalledWith('cs1', 'f1', 'f2')
    expect(useCompareStore.getState().pairs[0]?.match_method).toBe('manual')
    expect(useCompareStore.getState().error).toBeNull()
  })

  it('deletePair reloads the pair list on success', async () => {
    useCompareStore.setState({ compareSetId: 'cs1', pairs: [pairFixture()] })
    api.deletePair.mockResolvedValueOnce(undefined)
    api.getPairs.mockResolvedValueOnce([])

    await useCompareStore.getState().deletePair('pair1')

    expect(api.deletePair).toHaveBeenCalledWith('pair1')
    expect(useCompareStore.getState().pairs).toEqual([])
  })

  it('surfaces a real error message instead of swallowing it', async () => {
    useCompareStore.setState({ compareSetId: 'cs1' })
    api.getPairs.mockRejectedValueOnce(new Error('network down'))

    await useCompareStore.getState().loadPairs()

    expect(useCompareStore.getState().error).toBe('network down')
  })

  it('reset restores the initial screen/state', () => {
    useCompareStore.setState({
      screen: 'sheets',
      compareSetId: 'cs1',
      pairs: [pairFixture()],
      hasRunCompare: true,
      job: { id: 'x', kind: 'compare.run', progress: 0.5, message: null, stage: null },
    })

    useCompareStore.getState().reset()

    const state = useCompareStore.getState()
    expect(state.screen).toBe('set')
    expect(state.compareSetId).toBeNull()
    expect(state.pairs).toEqual([])
    expect(state.hasRunCompare).toBe(false)
    expect(state.job).toBeNull()
  })

  it('cancelActiveJob is a harmless no-op when no job is in flight', () => {
    expect(() => {
      useCompareStore.getState().cancelActiveJob()
    }).not.toThrow()
  })
})
