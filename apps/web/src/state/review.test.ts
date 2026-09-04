import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Change, Cluster, ClustersSidecar } from '../features/compare/reviewApi'

const api = vi.hoisted(() => ({
  getClusters: vi.fn(),
  getCompareDxf: vi.fn(),
  patchCluster: vi.fn(),
}))
vi.mock('../features/compare/reviewApi', () => ({
  getClusters: api.getClusters,
  getCompareDxf: api.getCompareDxf,
  patchCluster: api.patchCluster,
}))

/** The viewer facade (R1-00a's `features/viewer/host.ts`) is the seam: every
 * call the store makes into the CAD host goes through it, so mocking this one
 * module both keeps mlightcad out of jsdom and records the exact order
 * `loadPair` performs its steps in. */
const host = vi.hoisted(() => {
  const calls: string[] = []
  return {
    calls,
    layerStates: [] as { name: string; visible: boolean; frozen: boolean }[],
    openBytes: vi.fn(() => {
      calls.push('openBytes')
      return Promise.resolve()
    }),
    closeDrawing: vi.fn(() => {
      calls.push('closeDrawing')
      return Promise.resolve()
    }),
    setLayersVisible: vi.fn(() => {
      calls.push('setLayersVisible')
    }),
    whenRenderIdle: vi.fn(() => {
      calls.push('whenRenderIdle')
      return Promise.resolve()
    }),
    zoomTo: vi.fn(() => {
      calls.push('zoomTo')
    }),
    layers: vi.fn(() => host.layerStates),
    currentHost: vi.fn((): object | null => null),
    disposeCadHost: vi.fn(() => {
      calls.push('disposeCadHost')
      return Promise.resolve()
    }),
  }
})
vi.mock('../features/viewer/host', () => ({
  openBytes: host.openBytes,
  closeDrawing: host.closeDrawing,
  setLayersVisible: host.setLayersVisible,
  whenRenderIdle: host.whenRenderIdle,
  zoomTo: host.zoomTo,
  layers: host.layers,
  currentHost: host.currentHost,
  disposeCadHost: host.disposeCadHost,
}))

const {
  clusterOfHandles,
  clusterViewBox,
  layerVisibility,
  resetReviewViewerCache,
  useReviewStore,
  visibleCompareLayers,
} = await import('./review')

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
    cloud: {
      handle: '2F1',
      points: [
        [50, 150, 0.5],
        [350, 150, 0.5],
        [350, 450, 0.5],
        [50, 450, 0.5],
      ],
    },
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
    handle_to_cluster: { '2F1': 'c1', '2F2': 'c1', '2A1': 'c1' },
    counts: { clusters: clusters.length, changes: 1, minor: 0, approved: 0, ignored: 0 },
    ...overrides,
    clusters,
  }
}

function dxfBytes(): ArrayBuffer {
  return new Uint8Array([48, 10, 48, 10]).buffer
}

describe('layerVisibility', () => {
  it('overlay shows both compare layers, hides the label layer, keeps REV on', () => {
    expect(layerVisibility('overlay', 'REV-20260904')).toEqual({
      __CMP_ADDED: true,
      __CMP_REMOVED: true,
      __CMP_LABEL: false,
      'REV-20260904': true,
    })
  })

  it('전 hides __CMP_ADDED and 후 hides __CMP_REMOVED', () => {
    expect(layerVisibility('before', 'REV-20260904')).toMatchObject({
      __CMP_ADDED: false,
      __CMP_REMOVED: true,
    })
    expect(layerVisibility('after', 'REV-20260904')).toMatchObject({
      __CMP_ADDED: true,
      __CMP_REMOVED: false,
    })
  })

  it('omits the REV layer when the sidecar has not been loaded yet', () => {
    expect(Object.keys(layerVisibility('overlay', null))).toHaveLength(3)
  })
})

describe('clusterViewBox', () => {
  it('covers the cloud polyline and the badge, not just the change bbox', () => {
    expect(clusterViewBox(cluster())).toEqual({ minX: 50, minY: 150, maxX: 420, maxY: 520 })
  })

  it('falls back to the bbox when the cloud carries no points', () => {
    const bare = cluster({ cloud: { handle: null, points: [] }, badge: { center: [100, 200] } })
    expect(clusterViewBox(bare)).toEqual({ minX: 100, minY: 200, maxX: 300, maxY: 400 })
  })
})

describe('clusterOfHandles', () => {
  it('maps the first known handle through handle_to_cluster', () => {
    expect(clusterOfHandles(sidecar(), ['ZZZ', '2F2'])).toBe(1)
  })

  it('accepts a bare number as well as c<number> (contract §4)', () => {
    expect(clusterOfHandles(sidecar({ handle_to_cluster: { A1: '7' } }), ['A1'])).toBe(7)
  })

  it('is null for an unknown handle or no sidecar', () => {
    expect(clusterOfHandles(sidecar(), ['nope'])).toBeNull()
    expect(clusterOfHandles(null, ['2F1'])).toBeNull()
  })
})

describe('visibleCompareLayers', () => {
  it('keeps only the compare/REV layers that actually draw, sorted', () => {
    expect(
      visibleCompareLayers([
        { name: 'A-WALL', visible: true, frozen: false },
        { name: '__CMP_REMOVED', visible: true, frozen: false },
        { name: '__CMP_ADDED', visible: false, frozen: false },
        { name: 'REV-20260904', visible: true, frozen: true },
      ]),
    ).toEqual(['__CMP_REMOVED'])
  })
})

describe('useReviewStore', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    host.calls.length = 0
    host.layerStates = [
      { name: '__CMP_ADDED', visible: true, frozen: false },
      { name: '__CMP_REMOVED', visible: true, frozen: false },
      { name: 'REV-20260904', visible: true, frozen: false },
    ]
    resetReviewViewerCache()
    useReviewStore.setState(useReviewStore.getInitialState(), true)
  })

  it('loadPair fetches the sidecar, opens the DXF, waits for the render and applies the mode', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })

    await useReviewStore.getState().loadPair('pair-1')

    expect(host.calls).toEqual(['openBytes', 'whenRenderIdle', 'setLayersVisible', 'whenRenderIdle'])
    expect(host.setLayersVisible).toHaveBeenCalledWith({
      __CMP_ADDED: true,
      __CMP_REMOVED: true,
      __CMP_LABEL: false,
      'REV-20260904': true,
    })
    const state = useReviewStore.getState()
    expect(state.pairId).toBe('pair-1')
    expect(state.sidecar?.clusters).toHaveLength(1)
    expect(state.loading).toBe(false)
    expect(state.visibleLayers).toEqual(['__CMP_ADDED', '__CMP_REMOVED', 'REV-20260904'])
  })

  it('re-entering the same pair sends the cached ETag and does not re-open the drawing', async () => {
    api.getClusters.mockResolvedValue(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    api.getCompareDxf.mockResolvedValueOnce({ notModified: true, bytes: null, etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    expect(api.getCompareDxf).toHaveBeenLastCalledWith('pair-1', '"e1"')
    expect(host.openBytes).toHaveBeenCalledTimes(1)
  })

  it('a new ETag closes the old document and opens the new bytes', async () => {
    api.getClusters.mockResolvedValue(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e2"' })
    await useReviewStore.getState().loadPair('pair-1')

    expect(host.closeDrawing).toHaveBeenCalledWith('compare:pair-1')
    expect(host.openBytes).toHaveBeenCalledTimes(2)
  })

  it('two concurrent loads of the same pair share one open', async () => {
    api.getClusters.mockResolvedValue(sidecar())
    api.getCompareDxf.mockResolvedValue({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })

    await Promise.all([
      useReviewStore.getState().loadPair('pair-1'),
      useReviewStore.getState().loadPair('pair-1'),
    ])

    expect(host.openBytes).toHaveBeenCalledTimes(1)
  })

  it('throws away a viewer whose canvas is no longer in this screen\'s container', async () => {
    // Screen C unmounts on the way back to the sheet list, so the host it
    // created paints into a container React has since discarded; on the way in
    // it must be re-seated (measured as a black canvas on the second sheet).
    const container = document.createElement('div')
    container.id = 'viewer-root'
    document.body.append(container)
    host.currentHost.mockReturnValue({})
    api.getClusters.mockResolvedValue(sidecar())
    api.getCompareDxf.mockResolvedValue({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })

    await useReviewStore.getState().loadPair('pair-1')
    expect(host.disposeCadHost).toHaveBeenCalledTimes(1)
    expect(host.calls.indexOf('disposeCadHost')).toBeLessThan(host.calls.indexOf('openBytes'))

    // A container that already holds the canvas is left alone.
    container.append(document.createElement('canvas'))
    host.disposeCadHost.mockClear()
    await useReviewStore.getState().loadPair('pair-2')
    expect(host.disposeCadHost).not.toHaveBeenCalled()

    container.remove()
  })

  it('a sidecar failure leaves no list and reports the engine message', async () => {
    api.getClusters.mockRejectedValueOnce(new Error('clusters failed (409)'))

    await useReviewStore.getState().loadPair('pair-1')

    const state = useReviewStore.getState()
    expect(state.sidecar).toBeNull()
    expect(state.error).toContain('409')
    expect(host.openBytes).not.toHaveBeenCalled()
  })

  it('a render failure keeps the list and puts the message on the canvas', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    host.openBytes.mockRejectedValueOnce(new Error('the viewer refused to open the document'))

    await useReviewStore.getState().loadPair('pair-1')

    const state = useReviewStore.getState()
    expect(state.sidecar?.clusters).toHaveLength(1)
    expect(state.renderError).toContain('refused')
    expect(state.error).toBeNull()
  })

  it('select frames the cluster and remembers it', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    useReviewStore.getState().select(1)

    expect(useReviewStore.getState().selectedCluster).toBe(1)
    await vi.waitFor(() => {
      expect(host.zoomTo).toHaveBeenCalledWith({ minX: 50, minY: 150, maxX: 420, maxY: 520 }, 1.25)
    })
  })

  it('selectByHandles maps a hit test through the sidecar', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    useReviewStore.getState().selectByHandles(['2A1'])

    expect(useReviewStore.getState().selectedCluster).toBe(1)
  })

  it('selectStep walks the clusters and stops at the ends', async () => {
    api.getClusters.mockResolvedValueOnce(
      sidecar({ clusters: [cluster(), cluster({ id: 'c2', number: 2 })] }),
    )
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    const { selectStep } = useReviewStore.getState()
    selectStep(1)
    expect(useReviewStore.getState().selectedCluster).toBe(1)
    selectStep(1)
    expect(useReviewStore.getState().selectedCluster).toBe(2)
    selectStep(1)
    expect(useReviewStore.getState().selectedCluster).toBe(2)
    selectStep(-1)
    expect(useReviewStore.getState().selectedCluster).toBe(1)
  })

  it('decide updates the row before the PATCH answers, then keeps the server copy', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')

    let resolvePatch: ((value: Cluster) => void) | undefined
    api.patchCluster.mockReturnValueOnce(
      new Promise<Cluster>((resolve) => {
        resolvePatch = resolve
      }),
    )

    const pending = useReviewStore.getState().decide(1, 'approved')
    expect(useReviewStore.getState().sidecar?.clusters[0]?.decision).toBe('approved')
    expect(useReviewStore.getState().sidecar?.counts.approved).toBe(1)

    resolvePatch?.(cluster({ decision: 'approved', user_label: '문 이동' }))
    await pending

    expect(api.patchCluster).toHaveBeenCalledWith('pair-1', 1, { decision: 'approved' })
    expect(useReviewStore.getState().sidecar?.clusters[0]?.user_label).toBe('문 이동')
  })

  it('decide rolls the row back and surfaces the error when the PATCH fails', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')
    api.patchCluster.mockRejectedValueOnce(new Error('clusters/1 failed (500)'))

    await useReviewStore.getState().decide(1, 'ignored')

    const state = useReviewStore.getState()
    expect(state.sidecar?.clusters[0]?.decision).toBe('pending')
    expect(state.sidecar?.counts.ignored).toBe(0)
    expect(state.error).toContain('500')
  })

  it('pressing the same decision again returns the cluster to pending', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar({ clusters: [cluster({ decision: 'approved' })] }))
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')
    api.patchCluster.mockResolvedValueOnce(cluster({ decision: 'pending' }))

    await useReviewStore.getState().decide(1, 'approved')

    expect(api.patchCluster).toHaveBeenCalledWith('pair-1', 1, { decision: 'pending' })
  })

  it('an empty label clears user_label back to the engine wording', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar({ clusters: [cluster({ user_label: '문 이동' })] }))
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')
    api.patchCluster.mockResolvedValueOnce(cluster({ user_label: null }))

    await useReviewStore.getState().setLabel(1, '   ')

    expect(api.patchCluster).toHaveBeenCalledWith('pair-1', 1, { user_label: null })
    expect(useReviewStore.getState().sidecar?.clusters[0]?.user_label).toBeNull()
  })

  it('setNote writes the memo field only', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')
    api.patchCluster.mockResolvedValueOnce(cluster({ note: '현장 확인' }))

    await useReviewStore.getState().setNote(1, '현장 확인')

    expect(api.patchCluster).toHaveBeenCalledWith('pair-1', 1, { note: '현장 확인' })
  })

  it('setViewMode re-applies the layer map and re-reads what the host draws', async () => {
    api.getClusters.mockResolvedValueOnce(sidecar())
    api.getCompareDxf.mockResolvedValueOnce({ notModified: false, bytes: dxfBytes(), etag: '"e1"' })
    await useReviewStore.getState().loadPair('pair-1')
    host.layerStates = [
      { name: '__CMP_ADDED', visible: false, frozen: false },
      { name: '__CMP_REMOVED', visible: true, frozen: false },
      { name: 'REV-20260904', visible: true, frozen: false },
    ]

    await useReviewStore.getState().setViewMode('before')

    expect(host.setLayersVisible).toHaveBeenLastCalledWith({
      __CMP_ADDED: false,
      __CMP_REMOVED: true,
      __CMP_LABEL: false,
      'REV-20260904': true,
    })
    expect(useReviewStore.getState().visibleLayers).toEqual(['__CMP_REMOVED', 'REV-20260904'])
  })
})
