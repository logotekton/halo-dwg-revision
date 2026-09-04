import { engineFetch } from '../../api/engine'

/**
 * Engine client for `docs/contracts/r1.md` §7's `/compare/...` endpoints
 * (brief R1-05 Files-you-own). Field names mirror the wire JSON exactly
 * (snake_case) rather than being converted to camelCase at the boundary
 * the way `features/xref/api.ts` does -- these shapes (`CompareSetSummary`,
 * `SheetPair`, ...) are large, deeply nested, and specified field-by-field
 * in the contract itself (§3/§4/§7), so re-typing every field under a
 * second, hand-picked camelCase name would only add a translation step
 * that has to be kept in sync by hand with no real readability gain (see
 * this task's report "Decisions"). Types are a hand-kept mirror of
 * `packages/schema/gen/ts/compare/*.d.ts` rather than an import of that
 * package -- `apps/web` intentionally stays independent of workspace
 * packages it does not already depend on (the same reasoning
 * `apps/web/src/api/types.ts`'s own top comment gives for not importing
 * apps/desktop's types), and `@halo-cad/schema` is not yet a declared
 * dependency of this package (outside this task's "Files you own" --
 * `apps/web/package.json` -- see the report's "Shared-file patch").
 */

export type CompareSetStatus =
  | 'ingesting'
  | 'ingested'
  | 'extracting'
  | 'matched'
  | 'comparing'
  | 'compared'
  | 'exporting'
  | 'failed'

export type ConverterName = 'zwcad-com' | 'mlightcad-dxfout' | 'acad-ts'

export type ZwcadUnavailableReason = 'not_windows' | 'comtypes_missing' | 'not_registered' | 'com_error'

export interface ZwcadStatus {
  available: boolean
  installed: boolean
  version: string | null
  prog_id: string | null
  reason: ZwcadUnavailableReason | null
}

export interface CompareSetSide {
  set_id: string
  dir: string
  label: string
  files: number
  converted: number
  failed: number
  excluded: number
}

export interface CompareSetSummary {
  id: string
  project_id: string
  project_dir: string
  status: CompareSetStatus
  run_date: string
  before: CompareSetSide
  after: CompareSetSide
  converter: {
    before: ConverterName | null
    after: ConverterName | null
    mismatch_files: number
  }
  zwcad: ZwcadStatus
  fonts_missing: string[]
  crosscheck: { sampled: number; mismatched: number } | null
  frames: { before: number; after: number; unrecognized_files: number } | null
  pairs: {
    changed: number
    same: number
    added: number
    removed: number
    unpaired: number
    unrecognized: number
    converter_mismatch: number
    pending: number
  } | null
  last_job_id: string | null
}

export interface CompareFileEntry {
  id: string
  role: 'before' | 'after'
  original_name: string
  import_status: string
  converter: string | null
  excluded_reason: string | null
  error_message: string | null
  entity_count?: number | null
  parser_crosscheck?: unknown
  converter_meta?: Record<string, unknown> | null
}

export type PairStatus =
  | 'pending'
  | 'changed'
  | 'same'
  | 'added'
  | 'removed'
  | 'unpaired'
  | 'unrecognized'
  | 'converter_mismatch'

export type MatchMethod = 'number' | 'title' | 'position' | 'manual'

export interface SheetFrame {
  id: string
  compare_set_id: string
  role: 'before' | 'after'
  file_id: string
  kind: 'titleblock' | 'unrecognized_file'
  titleblock_handle?: string | null
  block_name?: string | null
  bbox: [number, number, number, number]
  sheet_no?: string | null
  sheet_title?: string | null
  scale_text?: string | null
  scale_denominator?: number | null
  date_text?: string | null
  norm_key: string
  sort_index: number
}

export interface SheetPair {
  id: string
  compare_set_id: string
  before_frame_id?: string | null
  after_frame_id?: string | null
  status: PairStatus
  match_method?: MatchMethod | null
  score?: number | null
  sort_key: string
  change_count: number
  minor_count: number
  cluster_count: number
  compare_dxf_path?: string | null
  clusters_json_path?: string | null
  warnings?: string[] | null
  before_frame?: SheetFrame | null
  after_frame?: SheetFrame | null
}

export type EngineJobStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED'

export interface EngineJobSummary {
  id: string
  status: EngineJobStatus
  progress: number
  message: string | null
  compare_set_id: string | null
  kind: string
  stage: string | null
  error?: string | null
}

/** Thrown by every request helper below so callers can branch on HTTP status
 * (in particular 404 for an R1-04/R1-06 endpoint not merged yet -- brief
 * "Defaults for ambiguity"). */
export class EngineHttpError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'EngineHttpError'
    this.status = status
  }
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await engineFetch(path, init)
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new EngineHttpError(res.status, `${path} failed (${String(res.status)}): ${detail}`)
  }
  return (await res.json()) as T
}

function jsonBody(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

/** `true` only for the "this endpoint's router is not mounted yet" case
 * (brief "Defaults for ambiguity": R1-04's `/frames`/`/pairs` and R1-06's
 * `/run` may 404 until their task merges). A 404 for an unknown id inside a
 * mounted router is a real error and must not be swallowed the same way --
 * this module only calls the not-yet-merged endpoints below, so any 404 it
 * sees is the "not merged" case in practice. */
function isNotMergedYet(err: unknown): boolean {
  return err instanceof EngineHttpError && err.status === 404
}

export async function getZwcadStatus(): Promise<ZwcadStatus> {
  return requestJson<ZwcadStatus>('/api/v1/compare/zwcad/status')
}

export interface CreateSetParams {
  beforeDir: string
  afterDir: string
  runDate: string
  projectDir?: string
}

export interface CreateSetResult {
  compareSetId: string
  projectId: string
  jobId: string
}

export async function createSet(params: CreateSetParams): Promise<CreateSetResult> {
  const dto = await requestJson<{ compare_set_id: string; project_id: string; job_id: string }>(
    '/api/v1/compare/sets',
    jsonBody({
      before_dir: params.beforeDir,
      after_dir: params.afterDir,
      run_date: params.runDate,
      project_dir: params.projectDir,
    }),
  )
  return { compareSetId: dto.compare_set_id, projectId: dto.project_id, jobId: dto.job_id }
}

export async function getSet(compareSetId: string): Promise<CompareSetSummary> {
  return requestJson<CompareSetSummary>(`/api/v1/compare/sets/${encodeURIComponent(compareSetId)}`)
}

export async function getSetFiles(compareSetId: string): Promise<CompareFileEntry[]> {
  return requestJson<CompareFileEntry[]>(`/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/files`)
}

/** `POST /compare/sets/{id}/frames` (R1-04). `null` when the router is not
 * merged yet -- caller shows the "준비 중" toast (brief "Defaults for
 * ambiguity"). */
export async function startFrames(compareSetId: string): Promise<{ jobId: string } | null> {
  try {
    const dto = await requestJson<{ job_id: string }>(
      `/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/frames`,
      { method: 'POST' },
    )
    return { jobId: dto.job_id }
  } catch (err) {
    if (isNotMergedYet(err)) return null
    throw err
  }
}

export interface PairQuery {
  status?: PairStatus
  q?: string
  sort?: string
}

function pairsQueryString(query: PairQuery): string {
  const params = new URLSearchParams()
  if (query.status) params.set('status', query.status)
  if (query.q) params.set('q', query.q)
  if (query.sort) params.set('sort', query.sort)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

/** `GET /compare/sets/{id}/pairs` (R1-04). `null` when the router is not
 * merged yet. */
export async function getPairs(compareSetId: string, query: PairQuery = {}): Promise<SheetPair[] | null> {
  try {
    return await requestJson<SheetPair[]>(
      `/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/pairs${pairsQueryString(query)}`,
    )
  } catch (err) {
    if (isNotMergedYet(err)) return null
    throw err
  }
}

/** `POST /compare/sets/{id}/pairs/manual` (R1-04). Only ever called from the
 * sheet list's manual-pair dialog, i.e. after `getPairs` already returned
 * non-null once -- so an unexpected 404 here is surfaced, not swallowed. */
export async function createManualPair(
  compareSetId: string,
  beforeFrameId: string,
  afterFrameId: string,
): Promise<SheetPair> {
  return requestJson<SheetPair>(
    `/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/pairs/manual`,
    jsonBody({ before_frame_id: beforeFrameId, after_frame_id: afterFrameId }),
  )
}

/** `DELETE /compare/pairs/{pair_id}` (R1-04, manual pairs only). */
export async function deletePair(pairId: string): Promise<void> {
  const res = await engineFetch(`/api/v1/compare/pairs/${encodeURIComponent(pairId)}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new EngineHttpError(res.status, `delete pair failed (${String(res.status)}): ${detail}`)
  }
}

/** `POST /compare/sets/{id}/run` (R1-06). `null` when the router is not
 * merged yet (brief "Defaults for ambiguity": "토스트 '비교 엔진 준비
 * 중'을 띄우고 상태를 유지한다"). */
export async function startRun(compareSetId: string, pairIds?: string[]): Promise<{ jobId: string } | null> {
  try {
    const dto = await requestJson<{ job_id: string }>(
      `/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/run`,
      jsonBody(pairIds && pairIds.length > 0 ? { pair_ids: pairIds } : {}),
    )
    return { jobId: dto.job_id }
  } catch (err) {
    if (isNotMergedYet(err)) return null
    throw err
  }
}

export async function getJob(jobId: string): Promise<EngineJobSummary> {
  return requestJson<EngineJobSummary>(`/api/v1/jobs/${encodeURIComponent(jobId)}`)
}

const TERMINAL_JOB_STATUSES: ReadonlySet<EngineJobStatus> = new Set(['DONE', 'FAILED', 'CANCELLED'])

export function isTerminalJobStatus(status: EngineJobStatus): boolean {
  return TERMINAL_JOB_STATUSES.has(status)
}

/**
 * Polls `GET /jobs/{id}` every `intervalMs` (brief R1-05 Goal 3: "잡 진행은
 * 기존 WS/폴링 방식을 재사용(없으면 `GET /jobs/{id}` 500ms 폴링)" -- no WS
 * job-progress client exists yet in `apps/web`, so this is that fallback).
 * `onUpdate` fires once per poll with the latest summary; the returned
 * `promise` resolves with the terminal summary. `cancel()` stops the loop
 * without throwing -- `state/compare.ts` calls it so a screen leaving mid-job
 * does not keep polling forever (brief Constraints: "잡 폴링은 화면을
 * 떠나도 새지 않게 정리").
 */
export function pollJob(
  jobId: string,
  onUpdate: (job: EngineJobSummary) => void,
  opts: { intervalMs?: number } = {},
): { promise: Promise<EngineJobSummary>; cancel: () => void } {
  const intervalMs = opts.intervalMs ?? 500
  const state = { cancelled: false }

  const promise = (async (): Promise<EngineJobSummary> => {
    for (;;) {
      const job = await getJob(jobId)
      if (state.cancelled) return job
      onUpdate(job)
      if (isTerminalJobStatus(job.status)) return job
      await new Promise<void>((resolve) => setTimeout(resolve, intervalMs))
    }
  })()

  return {
    promise,
    cancel: () => {
      state.cancelled = true
    },
  }
}
