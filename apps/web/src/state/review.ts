import { create } from 'zustand'
import {
  getClusters as apiGetClusters,
  getCompareDxf as apiGetCompareDxf,
  patchCluster as apiPatchCluster,
  type Cluster,
  type ClusterDecision,
  type ClusterPatch,
  type ClustersSidecar,
} from '../features/compare/reviewApi'

/**
 * The viewer facade, loaded the first time a sheet is actually opened.
 *
 * `features/viewer/host.ts` pulls in `@halo-cad/cad-core` and through it the
 * whole mlightcad stack. Screen C is the only screen that draws anything, so
 * a static import here would put the CAD engine in the app shell's module
 * graph -- every screen would carry it, and `app/App.test.tsx` (which renders
 * the shell and mocks nothing of the viewer) would have to load a WebGL
 * library inside jsdom. Deferring it also keeps mlightcad in its own chunk of
 * the built renderer.
 */
export type ViewerHostModule = typeof import('../features/viewer/host')
let viewerHostPromise: Promise<ViewerHostModule> | null = null

export function loadViewerHost(): Promise<ViewerHostModule> {
  viewerHostPromise ??= import('../features/viewer/host')
  return viewerHostPromise
}

/**
 * `review` store (docs/contracts/r1.md §9, brief R1-08 Goal 2) -- screen C's
 * half of the compare flow. `state/compare.ts` (R1-05) still owns which pair
 * is open (`selectedPairId`) and the sheet list's order; this store owns what
 * the viewer and the cluster panel show for that one pair.
 *
 * The renderer sends decisions and nothing else (brief Constraints:
 * "렌더러는 판정만 보낸다"): every box, cloud vertex and cluster number in
 * here was computed by the engine and arrives in the sidecar.
 */

export type ViewMode = 'overlay' | 'before' | 'after'

/** `docs/contracts/compare-dxf.md` §2 -- fixed layer names in the compare DXF. */
export const LAYER_ADDED = '__CMP_ADDED'
export const LAYER_REMOVED = '__CMP_REMOVED'
export const LAYER_LABEL = '__CMP_LABEL'

/**
 * `zoomTo`'s margin is a scale on the framed box, not a distance (CadHost:
 * "1.05 leaves a 5% border"). 1.25 keeps the cloud mark's arcs and the number
 * badge inside the viewport without the renderer having to know anything about
 * `compare.yaml`'s millimetre margins.
 */
export const CLUSTER_ZOOM_MARGIN = 1.25

/** The canvas container screen C mounts; the same id
 * `features/viewer/host.ts` exports as `VIEWER_ROOT_ID` and looks up when it
 * opens a drawing (kept as its own constant here so neither this store nor the
 * test hooks have to import the viewer module just for a string). */
export const REVIEW_CANVAS_ID = 'viewer-root'

/** Layer prefixes screen C reports back through {@link ReviewState.visibleLayers}. */
const COMPARE_LAYER_PREFIXES = ['__CMP_', 'REV-']

export interface FlatBox {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

/**
 * The layer visibility map for one view mode (`docs/contracts/compare-dxf.md`
 * §9): 겹쳐 보기 shows both `__CMP_*` layers, 전 hides `__CMP_ADDED`, 후 hides
 * `__CMP_REMOVED`. `REV-<YYYYMMDD>` is always on and `__CMP_LABEL` (the hit
 * rectangles) always off, so neither depends on the mode.
 */
export function layerVisibility(mode: ViewMode, revLayer: string | null): Record<string, boolean> {
  const entries: Record<string, boolean> = {
    [LAYER_ADDED]: mode !== 'before',
    [LAYER_REMOVED]: mode !== 'after',
    [LAYER_LABEL]: false,
  }
  if (revLayer) entries[revLayer] = true
  return entries
}

/**
 * The box the camera frames for a cluster.
 *
 * The cloud polyline's own vertices plus the badge centre, not `cluster.bbox`:
 * the bbox is the changed geometry alone, and framing it exactly would cut off
 * the cloud (bbox + `cloud.margin`) and the number badge that sits outside its
 * top-right corner (`docs/contracts/compare-dxf.md` §5). Both are engine
 * output read as-is -- no millimetre is computed here.
 */
export function clusterViewBox(cluster: Cluster): FlatBox {
  const [x0, y0, x1, y1] = cluster.bbox
  let minX = Math.min(x0, x1)
  let minY = Math.min(y0, y1)
  let maxX = Math.max(x0, x1)
  let maxY = Math.max(y0, y1)
  const points: [number, number][] = [
    ...cluster.cloud.points.map(([x, y]): [number, number] => [x, y]),
    cluster.badge.center,
  ]
  for (const [x, y] of points) {
    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
  }
  return { minX, minY, maxX, maxY }
}

/**
 * Cluster number for a hit-test result, or null.
 *
 * The sidecar's `handle_to_cluster` is the source of truth (contract §9); the
 * `c<n>` / bare `<n>` tolerance is `docs/contracts/compare-dxf.md` §4's note
 * that the compare DXF's XDATA spells the same number without the prefix.
 */
export function clusterOfHandles(sidecar: ClustersSidecar | null, handles: string[]): number | null {
  if (!sidecar) return null
  for (const handle of handles) {
    const id = sidecar.handle_to_cluster[handle]
    if (id === undefined) continue
    const number = Number.parseInt(id.startsWith('c') ? id.slice(1) : id, 10)
    if (Number.isFinite(number)) return number
  }
  return null
}

/** Compare-DXF layers the host currently draws, sorted -- what screen C
 * publishes as `data-cmp-visible` so a test can read the *host's* state and
 * not just the store's intent. */
export function visibleCompareLayers(
  layerStates: { name: string; visible: boolean; frozen: boolean }[],
): string[] {
  return layerStates
    .filter((layer) => COMPARE_LAYER_PREFIXES.some((prefix) => layer.name.startsWith(prefix)))
    .filter((layer) => layer.visible && !layer.frozen)
    .map((layer) => layer.name)
    .sort((a, b) => a.localeCompare(b))
}

/** Recomputes `counts.approved`/`counts.ignored` from the clusters themselves,
 * so an optimistic decision cannot leave the header disagreeing with the rows
 * until the next reload. */
function withCounts(sidecar: ClustersSidecar): ClustersSidecar {
  const approved = sidecar.clusters.filter((cluster) => cluster.decision === 'approved').length
  const ignored = sidecar.clusters.filter((cluster) => cluster.decision === 'ignored').length
  return { ...sidecar, counts: { ...sidecar.counts, approved, ignored } }
}

function replaceCluster(sidecar: ClustersSidecar, cluster: Cluster): ClustersSidecar {
  return withCounts({
    ...sidecar,
    clusters: sidecar.clusters.map((item) => (item.number === cluster.number ? cluster : item)),
  })
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** The viewer document id for a pair. One per sheet pair, so walking back into
 * a sheet reuses (or replaces) exactly its own document. */
export function compareFileId(pairId: string): string {
  return `compare:${pairId}`
}

/**
 * Compare-DXF bytes already fetched, keyed by pair id, with the ETag they came
 * with. Module scope rather than store state for the same reason
 * `state/compare.ts` keeps its poll-cancel handle there: this is a cache of
 * binary blobs, not something a component should ever render.
 */
const dxfCache = new Map<string, { etag: string | null; bytes: ArrayBuffer }>()
/** Newest-last; the oldest entry is dropped past this many sheets. */
const DXF_CACHE_LIMIT = 4

/** What the viewer currently holds, so a re-entry into the same sheet with an
 * unchanged ETag skips both the download and the re-open. */
let openedFileId: string | null = null
let openedEtag: string | null = null

/** One in-flight {@link ReviewState.loadPair} per pair: screen C's mount effect
 * and the `compareOpenPair` test hook both ask for the same sheet, and opening
 * one drawing twice into the same host is not a no-op. */
let inflight: { pairId: string; promise: Promise<void> } | null = null

/**
 * Throws the viewer away when its canvas is no longer in this screen's
 * container.
 *
 * The CAD host is a module-level singleton created around the `#viewer-root`
 * element of the *first* mount, and screen C unmounts every time the user goes
 * back to the sheet list. On the way in again React hands us a brand new,
 * empty container while the host still paints into the detached one -- which
 * looks exactly like a black canvas with a perfectly normal layer table
 * (measured: the second sheet of an e2e run rendered nothing at all). Only
 * `dispose` can re-seat it; `cad-core` has no `attach(container)` yet (see the
 * task report's shared-file patch).
 */
async function discardDetachedHost(host: ViewerHostModule): Promise<void> {
  const container = document.getElementById(REVIEW_CANVAS_ID)
  if (!container) return
  if (!host.currentHost() || container.childElementCount > 0) return
  await host.disposeCadHost()
  openedFileId = null
  openedEtag = null
}

function rememberBytes(pairId: string, etag: string | null, bytes: ArrayBuffer): void {
  dxfCache.set(pairId, { etag, bytes })
  while (dxfCache.size > DXF_CACHE_LIMIT) {
    const oldest = dxfCache.keys().next()
    if (oldest.done) break
    dxfCache.delete(oldest.value)
  }
}

/** Test-only: forgets the cached bytes and the "what is open" bookkeeping. */
export function resetReviewViewerCache(): void {
  dxfCache.clear()
  openedFileId = null
  openedEtag = null
  inflight = null
}

export interface ReviewState {
  /** Pair the store is showing; mirrors `compare.selectedPairId` once loaded. */
  pairId: string | null
  sidecar: ClustersSidecar | null
  viewMode: ViewMode
  selectedCluster: number | null
  /** "접힌 항목" list expanded. */
  showMinor: boolean
  loading: boolean
  /** Sidecar/PATCH failure, engine wording kept verbatim. */
  error: string | null
  /** Viewer failure (`openFailed`): the list stays, the canvas shows this. */
  renderError: string | null
  visibleLayers: string[]

  loadPair: (pairId: string) => Promise<void>
  select: (number: number | null) => void
  selectByHandles: (handles: string[]) => void
  selectStep: (delta: number) => void
  decide: (number: number, decision: ClusterDecision) => Promise<void>
  setLabel: (number: number, text: string) => Promise<void>
  setNote: (number: number, text: string) => Promise<void>
  setViewMode: (mode: ViewMode) => Promise<void>
  toggleMinor: () => void
  reset: () => void
}

const initialState = {
  pairId: null as string | null,
  sidecar: null as ClustersSidecar | null,
  viewMode: 'overlay' as ViewMode,
  selectedCluster: null as number | null,
  showMinor: false,
  loading: false,
  error: null as string | null,
  renderError: null as string | null,
  visibleLayers: [] as string[],
}

export const useReviewStore = create<ReviewState>()((set, get) => {
  /** Applies the mode's layer map and records what the host ended up drawing. */
  async function applyViewMode(mode: ViewMode): Promise<void> {
    const host = await loadViewerHost()
    const sidecar = get().sidecar
    host.setLayersVisible(layerVisibility(mode, sidecar?.layer ?? null))
    await host.whenRenderIdle()
    set({ visibleLayers: visibleCompareLayers(host.layers()) })
  }

  /**
   * Optimistic write-through: the cluster changes in the store first, the
   * `PATCH` follows, the server's answer replaces the optimistic copy, and a
   * failure puts the original row back and surfaces the message (brief Goal 2:
   * "낙관적 갱신 + PATCH, 실패 시 되돌림").
   */
  async function writeCluster(number: number, patch: ClusterPatch, next: (c: Cluster) => Cluster): Promise<void> {
    const sidecar = get().sidecar
    if (!sidecar) return
    const original = sidecar.clusters.find((cluster) => cluster.number === number)
    if (!original) return

    set({ sidecar: replaceCluster(sidecar, next(original)), error: null })
    try {
      const saved = await apiPatchCluster(sidecar.pair_id, number, patch)
      const current = get().sidecar
      if (current) set({ sidecar: replaceCluster(current, saved) })
    } catch (err) {
      const current = get().sidecar
      set({
        sidecar: current ? replaceCluster(current, original) : current,
        error: errorMessage(err),
      })
    }
  }

  /**
   * `GET clusters` -> `GET compare-dxf` (ETag) -> `openBytes` ->
   * `whenRenderIdle` -> layer mode (brief Goal 2, in that order). A sidecar
   * failure leaves nothing to show; a viewer failure keeps the list and puts
   * the message on the canvas (brief Constraints).
   */
  async function loadPairOnce(pairId: string): Promise<void> {
    set({
      pairId,
      loading: true,
      error: null,
      renderError: null,
      selectedCluster: null,
      visibleLayers: [],
    })

    let sidecar: ClustersSidecar
    try {
      sidecar = await apiGetClusters(pairId)
    } catch (err) {
      set({ loading: false, sidecar: null, error: errorMessage(err) })
      return
    }
    set({ sidecar })

    try {
      const cached = dxfCache.get(pairId)
      const result = await apiGetCompareDxf(pairId, cached?.etag ?? null)
      const bytes = result.notModified ? (cached?.bytes ?? null) : result.bytes
      const etag = result.notModified ? (cached?.etag ?? null) : result.etag
      if (!bytes) throw new Error(`compare DXF for ${pairId} was not returned`)
      if (!result.notModified) rememberBytes(pairId, etag, bytes)

      const host = await loadViewerHost()
      await discardDetachedHost(host)
      const fileId = compareFileId(pairId)
      if (openedFileId !== fileId || openedEtag !== etag) {
        if (openedFileId) await host.closeDrawing(openedFileId)
        openedFileId = null
        openedEtag = null
        // A copy: the host may transfer the buffer into a worker and detach
        // it, which would empty the cache entry for the next visit.
        await host.openBytes(fileId, `${sidecar.pair_key}.dxf`, bytes.slice(0))
        openedFileId = fileId
        openedEtag = etag
      }
      await host.whenRenderIdle()
      await applyViewMode(get().viewMode)
    } catch (err) {
      set({ renderError: errorMessage(err) })
    } finally {
      set({ loading: false })
    }
  }

  return {
    ...initialState,

    loadPair: async (pairId) => {
      if (inflight?.pairId === pairId) {
        await inflight.promise
        return
      }
      const promise = loadPairOnce(pairId).finally(() => {
        if (inflight?.pairId === pairId) inflight = null
      })
      inflight = { pairId, promise }
      await promise
    },

    /** Highlighting is immediate; the camera move rides on the viewer module's
     * promise, which is already resolved for every sheet after the first. */
    select: (number) => {
      set({ selectedCluster: number })
      if (number === null) return
      const cluster = get().sidecar?.clusters.find((item) => item.number === number)
      if (!cluster) return
      const box = clusterViewBox(cluster)
      void loadViewerHost().then((host) => {
        host.zoomTo(box, CLUSTER_ZOOM_MARGIN)
      })
    },

    selectByHandles: (handles) => {
      const number = clusterOfHandles(get().sidecar, handles)
      if (number !== null) get().select(number)
    },

    /** Keyboard J/K: the next/previous cluster in number order, stopping at
     * the ends (wrapping would hide "you have seen them all"). */
    selectStep: (delta) => {
      const clusters = get().sidecar?.clusters ?? []
      if (clusters.length === 0) return
      const current = get().selectedCluster
      const index = clusters.findIndex((cluster) => cluster.number === current)
      const nextIndex = index < 0 ? (delta > 0 ? 0 : clusters.length - 1) : index + delta
      const next = clusters[Math.min(Math.max(nextIndex, 0), clusters.length - 1)]
      if (next) get().select(next.number)
    },

    /** Pressing the same decision again returns the cluster to `pending`
     * (brief "Defaults for ambiguity": 판정 되돌리기). */
    decide: async (number, decision) => {
      const current = get().sidecar?.clusters.find((cluster) => cluster.number === number)
      if (!current) return
      const next: ClusterDecision = current.decision === decision ? 'pending' : decision
      await writeCluster(number, { decision: next }, (cluster) => ({ ...cluster, decision: next }))
    },

    /** Empty (or blank) text clears `user_label` back to the engine's own
     * label (brief "Defaults for ambiguity": 빈 문자열이면 `user_label: null`). */
    setLabel: async (number, text) => {
      const value = text.trim() === '' ? null : text
      await writeCluster(number, { user_label: value }, (cluster) => ({ ...cluster, user_label: value }))
    },

    setNote: async (number, text) => {
      const value = text.trim() === '' ? null : text
      await writeCluster(number, { note: value }, (cluster) => ({ ...cluster, note: value }))
    },

    setViewMode: async (mode) => {
      set({ viewMode: mode })
      await applyViewMode(mode)
    },

    toggleMinor: () => {
      set((state) => ({ showMinor: !state.showMinor }))
    },

    reset: () => {
      set({ ...initialState })
    },
  }
})
