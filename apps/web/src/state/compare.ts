import { create } from 'zustand'
import {
  createManualPair as apiCreateManualPair,
  createSet as apiCreateSet,
  deletePair as apiDeletePair,
  getPairs as apiGetPairs,
  getSet as apiGetSet,
  getSetFiles as apiGetSetFiles,
  getZwcadStatus as apiGetZwcadStatus,
  pollJob,
  startFrames as apiStartFrames,
  startRun as apiStartRun,
  type CompareFileEntry,
  type CompareSetSummary,
  type EngineJobSummary,
  type SheetPair,
  type ZwcadStatus,
} from '../features/compare/api'
import { DEFAULT_PAIR_FILTERS, type PairFilters } from '../features/compare/pairFilters'
import { pickFolder } from '../features/compare/ipc'

/**
 * `compare` store (docs/contracts/r1.md §9). Screens A-D are one linear
 * flow driven entirely by `screen` -- there is no router, per brief
 * "Defaults for ambiguity": "화면 전환에 라우터 라이브러리 금지(스토어
 * `screen`으로만)".
 */
export type CompareScreen = 'set' | 'sheets' | 'review' | 'export'

export interface CompareJobState {
  id: string
  kind: string
  progress: number
  message: string | null
  stage: string | null
}

function todayIsoDate(): string {
  // The renderer's own "today", per contract §11: "run_date는 렌더러가
  // 화면 A에서 입력(기본값은 렌더러의 오늘 날짜, e2e는 고정값)". The engine
  // itself never calls the clock for anything that ends up in an artefact.
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${String(year)}-${month}-${day}`
}

function jobStateFrom(job: EngineJobSummary): CompareJobState {
  return { id: job.id, kind: job.kind, progress: job.progress, message: job.message, stage: job.stage }
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/**
 * Cancel handle for whichever job poll is currently running, module-scoped
 * (not store state) because it holds a function, not serialisable data --
 * the same pattern `api/engine.ts`'s `connectionPromise` uses. `state/
 * compare.ts`'s own `cancelActiveJob` action is what a screen's `useEffect`
 * cleanup calls (brief Constraints: "잡 폴링은 화면을 떠나도 새지 않게
 * 정리").
 */
let activeJobCancel: (() => void) | null = null

async function runJobToCompletion(
  jobId: string,
  kind: string,
  onUpdate: (job: CompareJobState) => void,
): Promise<EngineJobSummary> {
  const { promise, cancel } = pollJob(jobId, (job) => {
    onUpdate(jobStateFrom(job))
  })
  activeJobCancel = cancel
  try {
    return await promise
  } finally {
    activeJobCancel = null
  }
}

export interface CompareState {
  screen: CompareScreen
  projectDir: string | null
  beforeDir: string | null
  afterDir: string | null
  runDate: string
  compareSetId: string | null
  summary: CompareSetSummary | null
  files: CompareFileEntry[]
  job: CompareJobState | null
  pairs: SheetPair[]
  /** `true` once `GET .../pairs` has returned 200 at least once (R1-04
   * merged) -- distinguishes "no pairs yet" from "the endpoint does not
   * exist in this build" (brief: e2e must branch on this). */
  pairsAvailable: boolean
  filters: PairFilters
  selectedPairId: string | null
  zwcad: ZwcadStatus | null
  /** `POST .../run` has completed at least once -- screen B's "도곽 열기"/
   * "전체 도곽 출력" stay disabled before this (brief Goal 5). */
  hasRunCompare: boolean
  /** i18n key for a transient banner (e.g. an endpoint not merged yet), or
   * `null`. Never pre-translated text -- screens call `t(toast)`. */
  toast: string | null
  /** Raw (untranslated, often engine-supplied) error text, or `null`. */
  error: string | null
  busy: boolean

  pickBefore: () => Promise<void>
  pickAfter: () => Promise<void>
  setRunDate: (date: string) => void
  loadZwcadStatus: () => Promise<void>
  startSet: () => Promise<void>
  startFrames: () => Promise<void>
  refreshSummary: () => Promise<void>
  loadPairs: () => Promise<void>
  setFilters: (patch: Partial<PairFilters>) => void
  selectPair: (pairId: string | null) => void
  openPair: (pairId: string) => void
  createManualPair: (beforeFrameId: string, afterFrameId: string) => Promise<void>
  deletePair: (pairId: string) => Promise<void>
  startRun: (pairIds?: string[]) => Promise<void>
  goto: (screen: CompareScreen) => void
  dismissToast: () => void
  cancelActiveJob: () => void
  reset: () => void
}

const initialState = {
  screen: 'set' as CompareScreen,
  projectDir: null as string | null,
  beforeDir: null as string | null,
  afterDir: null as string | null,
  runDate: todayIsoDate(),
  compareSetId: null as string | null,
  summary: null as CompareSetSummary | null,
  files: [] as CompareFileEntry[],
  job: null as CompareJobState | null,
  pairs: [] as SheetPair[],
  pairsAvailable: false,
  filters: DEFAULT_PAIR_FILTERS,
  selectedPairId: null as string | null,
  zwcad: null as ZwcadStatus | null,
  hasRunCompare: false,
  toast: null as string | null,
  error: null as string | null,
  busy: false,
}

export const useCompareStore = create<CompareState>()((set, get) => ({
  ...initialState,

  pickBefore: async () => {
    const picked = await pickFolder()
    if (picked) set({ beforeDir: picked })
  },

  pickAfter: async () => {
    const picked = await pickFolder()
    if (picked) set({ afterDir: picked })
  },

  setRunDate: (date) => {
    set({ runDate: date })
  },

  loadZwcadStatus: async () => {
    try {
      const zwcad = await apiGetZwcadStatus()
      set({ zwcad })
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  refreshSummary: async () => {
    const { compareSetId } = get()
    if (!compareSetId) return
    try {
      const [summary, files] = await Promise.all([apiGetSet(compareSetId), apiGetSetFiles(compareSetId)])
      set({ summary, files })
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  startSet: async () => {
    const { beforeDir, afterDir, runDate } = get()
    if (!beforeDir || !afterDir) return
    set({ busy: true, error: null, toast: null })
    try {
      const created = await apiCreateSet({ beforeDir, afterDir, runDate })
      set({
        compareSetId: created.compareSetId,
        job: { id: created.jobId, kind: 'compare.ingest', progress: 0, message: null, stage: null },
      })
      await get().refreshSummary()

      const finalJob = await runJobToCompletion(created.jobId, 'compare.ingest', (job) => {
        set({ job })
      })
      await get().refreshSummary()

      if (finalJob.status !== 'DONE') {
        set({ busy: false, job: null, error: finalJob.error ?? `ingest job ${finalJob.status}` })
        return
      }

      await get().startFrames()
    } catch (err) {
      set({ busy: false, job: null, error: errorMessage(err) })
    }
  },

  startFrames: async () => {
    const { compareSetId } = get()
    if (!compareSetId) return
    set({ busy: true, toast: null, error: null })
    try {
      const started = await apiStartFrames(compareSetId)
      if (started === null) {
        // R1-04's router is not merged yet (brief "Defaults for ambiguity").
        set({ busy: false, job: null, toast: 'compare.set.toast.framesNotReady' })
        return
      }
      set({ job: { id: started.jobId, kind: 'compare.frames', progress: 0, message: null, stage: null } })

      const finalJob = await runJobToCompletion(started.jobId, 'compare.frames', (job) => {
        set({ job })
      })
      await get().refreshSummary()

      if (finalJob.status !== 'DONE') {
        set({ busy: false, job: null, error: finalJob.error ?? `frames job ${finalJob.status}` })
        return
      }

      set({ job: null, busy: false })
      await get().loadPairs()
      get().goto('sheets')
    } catch (err) {
      set({ busy: false, job: null, error: errorMessage(err) })
    }
  },

  loadPairs: async () => {
    const { compareSetId, filters } = get()
    if (!compareSetId) return
    try {
      const pairs = await apiGetPairs(compareSetId, { q: filters.q || undefined })
      if (pairs === null) {
        set({ pairs: [], pairsAvailable: false })
        return
      }
      set({ pairs, pairsAvailable: true })
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  setFilters: (patch) => {
    set((state) => ({ filters: { ...state.filters, ...patch } }))
  },

  selectPair: (pairId) => {
    set({ selectedPairId: pairId })
  },

  openPair: (pairId) => {
    set({ selectedPairId: pairId })
    get().goto('review')
  },

  createManualPair: async (beforeFrameId, afterFrameId) => {
    const { compareSetId } = get()
    if (!compareSetId) return
    set({ busy: true, error: null })
    try {
      await apiCreateManualPair(compareSetId, beforeFrameId, afterFrameId)
      await get().loadPairs()
      set({ busy: false })
    } catch (err) {
      set({ busy: false, error: errorMessage(err) })
    }
  },

  deletePair: async (pairId) => {
    set({ busy: true, error: null })
    try {
      await apiDeletePair(pairId)
      await get().loadPairs()
      set({ busy: false })
    } catch (err) {
      set({ busy: false, error: errorMessage(err) })
    }
  },

  startRun: async (pairIds) => {
    const { compareSetId } = get()
    if (!compareSetId) return
    set({ busy: true, toast: null, error: null })
    try {
      const started = await apiStartRun(compareSetId, pairIds)
      if (started === null) {
        // R1-06's router is not merged yet (brief "Defaults for ambiguity":
        // "토스트 '비교 엔진 준비 중'을 띄우고 상태를 유지한다").
        set({ busy: false, toast: 'compare.sheets.toast.runNotReady' })
        return
      }
      set({ job: { id: started.jobId, kind: 'compare.run', progress: 0, message: null, stage: null } })

      const finalJob = await runJobToCompletion(started.jobId, 'compare.run', (job) => {
        set({ job })
      })

      if (finalJob.status !== 'DONE') {
        set({ busy: false, job: null, error: finalJob.error ?? `run job ${finalJob.status}` })
        return
      }

      set({ job: null, busy: false, hasRunCompare: true })
      await Promise.all([get().loadPairs(), get().refreshSummary()])
    } catch (err) {
      set({ busy: false, job: null, error: errorMessage(err) })
    }
  },

  goto: (screen) => {
    set({ screen })
  },

  dismissToast: () => {
    set({ toast: null })
  },

  cancelActiveJob: () => {
    activeJobCancel?.()
    activeJobCancel = null
  },

  reset: () => {
    get().cancelActiveJob()
    set({ ...initialState, runDate: todayIsoDate() })
  },
}))
