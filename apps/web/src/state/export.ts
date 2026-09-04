import { create } from 'zustand'
import { pollJob, type EngineJobSummary } from '../features/compare/api'
import {
  getRun as apiGetRun,
  getRunTsv as apiGetRunTsv,
  startExport as apiStartExport,
  type Run,
} from '../features/compare/exportApi'
import { copyToClipboard, openInOS } from '../features/compare/ipc'

/**
 * `export` store (docs/contracts/r1.md §9, brief R1-10 Goal 2) -- screen D's
 * half of the compare flow. `state/compare.ts` still owns which
 * `compare_set_id` is active; this store owns the one export request that set
 * has made and its result, the same separation `state/review.ts` keeps for
 * screen C's one open pair.
 */

export interface ExportJobState {
  id: string
  kind: string
  progress: number
  message: string | null
  stage: string | null
}

function jobStateFrom(job: EngineJobSummary): ExportJobState {
  return { id: job.id, kind: job.kind, progress: job.progress, message: job.message, stage: job.stage }
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Cancel handle for the export job's poll, module-scoped for the same
 * reason `state/compare.ts`'s `activeJobCancel` is: it holds a function, not
 * serialisable store data. `cancelActiveJob` is what screen D's unmount
 * effect calls (brief Constraints: "잡 폴링 정리"). */
let activeJobCancel: (() => void) | null = null

/** Timer for the "TSV 복사됨" toast's 2-second auto-dismiss (brief "Defaults
 * for ambiguity": "TSV 복사 성공 토스트 2초"). Module-scoped so `reset()` can
 * clear a pending one instead of leaving it to fire after the store has moved
 * on to a different run. */
let toastTimer: ReturnType<typeof setTimeout> | null = null

function clearToastTimer(): void {
  if (toastTimer !== null) {
    clearTimeout(toastTimer)
    toastTimer = null
  }
}

export interface RunExportParams {
  compareSetId: string
  runDate: string
}

export interface ExportState {
  /** Screen D's own run-date field. Defaults to the compare set's `run_date`
   * (contract §9), but editing it only changes this store's next export
   * request -- the compare DXF and its clusters are untouched (brief
   * "Defaults for ambiguity"). */
  runDate: string
  run: Run | null
  exportJob: ExportJobState | null
  busy: boolean
  /** Engine wording kept verbatim, same convention as `state/compare.ts`. */
  error: string | null
  /** i18n key for a transient banner (the TSV-copied toast) -- never
   * pre-translated text, screens call `t(toast)`. */
  toast: string | null

  setRunDate: (date: string) => void
  runExport: (params: RunExportParams) => Promise<void>
  copyTsv: () => Promise<void>
  openOutput: () => Promise<void>
  cancelActiveJob: () => void
  reset: () => void
}

const initialState = {
  runDate: '',
  run: null as Run | null,
  exportJob: null as ExportJobState | null,
  busy: false,
  error: null as string | null,
  toast: null as string | null,
}

export const useExportStore = create<ExportState>()((set, get) => ({
  ...initialState,

  setRunDate: (date) => {
    set({ runDate: date })
  },

  /** `POST .../export` -> `GET /jobs/{id}` polling to completion -> `GET
   * .../runs/{id}` for the finished `Run` (brief Goal 1: "출력 실행" → export
   * job → progress → result table). A non-`DONE` job leaves `run` untouched
   * and surfaces the engine's error with a retry (screen D keeps the "출력
   * 실행" button enabled). */
  runExport: async ({ compareSetId, runDate }) => {
    set({ busy: true, error: null, toast: null, run: null, exportJob: null })
    try {
      const started = await apiStartExport(compareSetId, { runDate })
      set({ exportJob: { id: started.jobId, kind: 'compare.export', progress: 0, message: null, stage: null } })

      const { promise, cancel } = pollJob(started.jobId, (job) => {
        set({ exportJob: jobStateFrom(job) })
      })
      activeJobCancel = cancel
      let finalJob: EngineJobSummary
      try {
        finalJob = await promise
      } finally {
        activeJobCancel = null
      }

      if (finalJob.status !== 'DONE') {
        set({ busy: false, exportJob: null, error: finalJob.error ?? `export job ${finalJob.status}` })
        return
      }

      const run = await apiGetRun(started.runId)
      set({ busy: false, exportJob: null, run })
    } catch (err) {
      set({ busy: false, exportJob: null, error: errorMessage(err) })
    }
  },

  /** `GET .../tsv` -> `clipboard.writeText` (brief Goal 1: "변경 리스트 TSV
   * 복사"). No-op before a run exists. */
  copyTsv: async () => {
    const run = get().run
    if (!run) return
    set({ error: null })
    try {
      const text = await apiGetRunTsv(run.id)
      await copyToClipboard(text)
      clearToastTimer()
      set({ toast: 'compare.export.toast.tsvCopied' })
      toastTimer = setTimeout(() => {
        toastTimer = null
        if (get().toast === 'compare.export.toast.tsvCopied') set({ toast: null })
      }, 2_000)
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  /** `shell.openPath(run.output_dir)` (brief Goal 1: "폴더 열기"). */
  openOutput: async () => {
    const run = get().run
    if (!run) return
    try {
      await openInOS(run.output_dir)
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  cancelActiveJob: () => {
    activeJobCancel?.()
    activeJobCancel = null
  },

  reset: () => {
    get().cancelActiveJob()
    clearToastTimer()
    set({ ...initialState })
  },
}))
