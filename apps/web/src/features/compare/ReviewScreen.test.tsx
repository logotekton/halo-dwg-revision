import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { useCompareStore } from '../../state/compare'
import type { Change, Cluster, ClustersSidecar } from './reviewApi'
import type { SheetPair } from './api'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const reviewApi = vi.hoisted(() => ({
  getClusters: vi.fn(),
  getCompareDxf: vi.fn(),
  patchCluster: vi.fn(),
}))
vi.mock('./reviewApi', () => ({
  getClusters: reviewApi.getClusters,
  getCompareDxf: reviewApi.getCompareDxf,
  patchCluster: reviewApi.patchCluster,
}))

/** The CadHost facade -- mocked so jsdom never loads mlightcad or WebGL, and
 * so the screen's viewer calls are observable. */
const host = vi.hoisted(() => ({
  openBytes: vi.fn(() => Promise.resolve()),
  closeDrawing: vi.fn(() => Promise.resolve()),
  setLayersVisible: vi.fn(),
  whenRenderIdle: vi.fn(() => Promise.resolve()),
  zoomTo: vi.fn(),
  layers: vi.fn(() => [] as { name: string; visible: boolean; frozen: boolean }[]),
  onSelection: vi.fn(() => () => undefined),
  currentHost: vi.fn((): object | null => null),
  disposeCadHost: vi.fn(() => Promise.resolve()),
  VIEWER_ROOT_ID: 'viewer-root',
}))
vi.mock('../viewer/host', () => host)

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, getPairs: vi.fn(), startRun: vi.fn(), pollJob: vi.fn() }
})
vi.mock('./ipc', () => ({ pickFolder: vi.fn(), copyToClipboard: vi.fn(), openInOS: vi.fn() }))

const { useReviewStore, resetReviewViewerCache } = await import('../../state/review')
const { ReviewScreen } = await import('./ReviewScreen')

function cluster(overrides: Partial<Cluster> = {}): Cluster {
  return {
    id: 'c1',
    number: 1,
    bbox: [100, 200, 300, 400],
    kind: 'moved',
    label: '블록 DOOR_900 이동 1,250mm 동',
    user_label: null,
    decision: 'pending',
    note: null,
    change_ids: ['ch1'],
    cloud: { handle: '2F1', points: [[50, 150, 0.5]] },
    badge: { shape_handle: '2F2', text_handle: '2F3', center: [420, 520] },
    ...overrides,
  }
}

function change(overrides: Partial<Change> = {}): Change {
  return {
    id: 'ch1',
    seq: 1,
    kind: 'moved',
    etype: 'INSERT',
    layer: 'A-DOOR',
    bbox: [100, 200, 300, 400],
    minor: false,
    minor_reason: null,
    cluster_id: 'c1',
    provenance: {},
    ...overrides,
  }
}

function sidecar(overrides: Partial<ClustersSidecar> = {}): ClustersSidecar {
  const clusters = overrides.clusters ?? [cluster()]
  return {
    schema_version: '0.1',
    pair_id: 'pair-1',
    pair_key: 'A-101',
    run_date: '2026-09-04',
    layer: 'REV-20260904',
    frame: { bbox: [0, 0, 84100, 59400], scale_denominator: 100, scale_factor: 1, offset_before: [0, 0] },
    changes: [change()],
    handle_to_cluster: { '2F1': 'c1' },
    counts: { clusters: clusters.length, changes: 1, minor: 0, approved: 0, ignored: 0 },
    ...overrides,
    clusters,
  }
}

function pair(overrides: Partial<SheetPair> = {}): SheetPair {
  return {
    id: 'pair-1',
    compare_set_id: 'cs1',
    before_frame_id: 'f1',
    after_frame_id: 'f2',
    status: 'changed',
    match_method: 'number',
    sort_key: 'A-101',
    change_count: 1,
    minor_count: 0,
    cluster_count: 1,
    compare_dxf_path: '/cs1/pair-1/compare.dxf',
    after_frame: {
      id: 'f2',
      compare_set_id: 'cs1',
      role: 'after',
      file_id: 'file2',
      kind: 'titleblock',
      bbox: [0, 0, 84100, 59400],
      sheet_no: 'A-101',
      sheet_title: '1층 평면도',
      norm_key: 'A-101',
      sort_index: 0,
    },
    ...overrides,
  }
}

/** Puts the screen in "pair loaded" state without going through `loadPair`,
 * so a test can assert on the panel without driving the viewer. */
function showSidecar(value: ClustersSidecar, pairs: SheetPair[] = [pair()]): void {
  useCompareStore.setState({ screen: 'review', selectedPairId: value.pair_id, pairs, pairsAvailable: true })
  useReviewStore.setState({ pairId: value.pair_id, sidecar: value, loading: false })
}

describe('ReviewScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetReviewViewerCache()
    useCompareStore.setState(useCompareStore.getInitialState(), true)
    useReviewStore.setState(useReviewStore.getInitialState(), true)
    reviewApi.getClusters.mockResolvedValue(sidecar())
    reviewApi.getCompareDxf.mockResolvedValue({
      notModified: false,
      bytes: new Uint8Array([48, 10]).buffer,
      etag: '"e1"',
    })
    reviewApi.patchCluster.mockImplementation((_pairId: string, number: number, patch: Partial<Cluster>) =>
      Promise.resolve(cluster({ number, ...patch })),
    )
  })

  afterEach(() => {
    cleanup()
  })

  it('mounts the viewer container and loads the selected pair', async () => {
    useCompareStore.setState({ screen: 'review', selectedPairId: 'pair-1', pairs: [pair()], pairsAvailable: true })
    render(<ReviewScreen />)

    expect(document.getElementById('viewer-root')).not.toBeNull()
    await waitFor(() => {
      expect(host.openBytes).toHaveBeenCalledTimes(1)
    })
    expect(reviewApi.getClusters).toHaveBeenCalledWith('pair-1')
  })

  it('renders one row per cluster with its number, kind, label and decision', () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(1)
    const row = within(screen.getByTestId('cluster-row-1'))
    expect(row.getByText('1')).toBeInTheDocument()
    expect(row.getByText('이동')).toBeInTheDocument()
    expect(row.getByText('블록 DOOR_900 이동 1,250mm 동')).toBeInTheDocument()
    expect(screen.getByTestId('cluster-decision-1')).toHaveTextContent('대기')
    expect(screen.getByText('A-101')).toBeInTheDocument()
  })

  it('clicking the number badge frames that cluster', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    fireEvent.click(screen.getByTestId('cluster-number-1'))

    expect(useReviewStore.getState().selectedCluster).toBe(1)
    await waitFor(() => {
      expect(host.zoomTo).toHaveBeenCalledWith({ minX: 50, minY: 150, maxX: 420, maxY: 520 }, 1.25)
    })
  })

  it('승인 sends the decision and shows it on the chip', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    fireEvent.click(screen.getByTestId('cluster-approve-1'))

    await waitFor(() => {
      expect(reviewApi.patchCluster).toHaveBeenCalledWith('pair-1', 1, { decision: 'approved' })
    })
    expect(screen.getByTestId('cluster-decision-1')).toHaveTextContent('승인')
  })

  it('무시 sends the other decision', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    fireEvent.click(screen.getByTestId('cluster-ignore-1'))

    await waitFor(() => {
      expect(reviewApi.patchCluster).toHaveBeenCalledWith('pair-1', 1, { decision: 'ignored' })
    })
  })

  it('editing the label saves on Enter and cancels on Escape', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    fireEvent.click(screen.getByRole('button', { name: '1번 문구 편집' }))
    const input = screen.getByRole('textbox', { name: '1번 문구 편집' })
    fireEvent.change(input, { target: { value: '문 위치 조정' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(reviewApi.patchCluster).toHaveBeenCalledWith('pair-1', 1, { user_label: '문 위치 조정' })
    })

    vi.clearAllMocks()
    fireEvent.click(screen.getByRole('button', { name: '1번 문구 편집' }))
    const second = screen.getByRole('textbox', { name: '1번 문구 편집' })
    fireEvent.change(second, { target: { value: '취소될 문구' } })
    fireEvent.keyDown(second, { key: 'Escape' })

    expect(reviewApi.patchCluster).not.toHaveBeenCalled()
  })

  it('the view mode buttons only change layer visibility', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)
    await waitFor(() => {
      expect(host.openBytes).toHaveBeenCalledTimes(1)
    })
    host.openBytes.mockClear()

    fireEvent.click(screen.getByRole('button', { name: '전' }))

    await waitFor(() => {
      expect(host.setLayersVisible).toHaveBeenCalledWith({
        __CMP_ADDED: false,
        __CMP_REMOVED: true,
        __CMP_LABEL: false,
        'REV-20260904': true,
      })
    })
    expect(host.openBytes).not.toHaveBeenCalled()
    expect(useReviewStore.getState().viewMode).toBe('before')
  })

  it('"접힌 항목" expands into one row per fold reason', () => {
    showSidecar(
      sidecar({
        clusters: [],
        changes: [
          change({ id: 'ch1', seq: 1, minor: true, minor_reason: 'layer_only', cluster_id: null }),
          change({ id: 'ch2', seq: 2, minor: true, minor_reason: 'layer_only', cluster_id: null }),
          change({ id: 'ch3', seq: 3, minor: true, minor_reason: 'color_only', cluster_id: null }),
        ],
      }),
    )
    render(<ReviewScreen />)

    expect(screen.queryByTestId('minor-list')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('minor-toggle'))

    const list = within(screen.getByTestId('minor-list'))
    expect(list.getByText('레이어만')).toBeInTheDocument()
    expect(list.getByText('색만')).toBeInTheDocument()
    expect(screen.getByTestId('minor-toggle')).toHaveTextContent('접힌 항목 3건')
  })

  it('keeps the cluster list and shows the message when the drawing fails to open', async () => {
    host.openBytes.mockRejectedValueOnce(new Error('the viewer refused to open the document'))
    useCompareStore.setState({ screen: 'review', selectedPairId: 'pair-1', pairs: [pair()], pairsAvailable: true })
    render(<ReviewScreen />)

    expect(await screen.findByTestId('review-render-error')).toBeInTheDocument()
    expect(screen.getByTestId('cluster-row-1')).toBeInTheDocument()
  })

  it('이전/다음 도곽 walks screen B\'s order and 목록으로 goes back', () => {
    const pairs = [pair(), pair({ id: 'pair-2', sort_key: 'A-102' })]
    showSidecar(sidecar(), pairs)
    render(<ReviewScreen />)

    expect(screen.getByRole('button', { name: '이전 도곽' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: '다음 도곽' }))
    expect(useCompareStore.getState().selectedPairId).toBe('pair-2')

    fireEvent.click(screen.getByRole('button', { name: '도곽 목록으로' }))
    expect(useCompareStore.getState().screen).toBe('sheets')
  })

  it('keyboard: J selects, A approves', async () => {
    showSidecar(sidecar())
    render(<ReviewScreen />)

    fireEvent.keyDown(window, { key: 'j' })
    expect(useReviewStore.getState().selectedCluster).toBe(1)

    fireEvent.keyDown(window, { key: 'a' })
    await waitFor(() => {
      expect(reviewApi.patchCluster).toHaveBeenCalledWith('pair-1', 1, { decision: 'approved' })
    })
  })
})
