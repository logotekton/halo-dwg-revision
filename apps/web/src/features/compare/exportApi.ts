import { engineFetch } from '../../api/engine'
import { EngineHttpError } from './api'

/**
 * Engine client for screen D's three endpoints (`docs/contracts/r1.md` §7,
 * R1-09's `api/routers/compare_export.py`, described in
 * `docs/dev/compare-export.md`):
 *
 * - `POST /compare/sets/{id}/export`   -> `202 {job_id, run_id}`
 * - `GET  /compare/runs/{run_id}`      -> {@link Run} (API shape: absolute
 *   `files[].path`, no `schema_version`, a `created_at`)
 * - `GET  /compare/runs/{run_id}/tsv`  -> `changes.tsv`'s bytes as text
 *
 * `Run`/`RunOutputFile` are a hand-kept snake_case mirror of
 * `packages/schema/gen/ts/compare/run.d.ts`, for the same two reasons
 * `features/compare/api.ts` (R1-05) and `reviewApi.ts` (R1-08) give at the
 * top of their own files: adding `@halo-cad/schema` to `apps/web/package.json`
 * is outside this task's "Files you own", and the renderer already keeps
 * that kind of mirror by convention (`apps/web/src/api/types.ts`).
 */

export type RunScope = 'all'

export type RunMethod = 'auto' | 'zwcad' | 'acad-ts' | 'dxf-only'

/** Which writer actually produced one file. `dxf-only` means no DWG writer
 * was available (or the one that was tried failed) and a `.dxf` was written
 * in its place. */
export type OutputWriter = 'zwcad-com' | 'acad-ts' | 'dxf-only'

export type RunStatus = 'running' | 'done' | 'failed'

export interface RunOutputFile {
  pair_id: string
  /** Null when the sheet had no drawing number (the source file name was
   * used for the file name instead). */
  sheet_no: string | null
  /** Absolute path (API shape) inside `output_dir`. */
  path: string
  format: 'dwg' | 'dxf'
  writer: OutputWriter
}

export interface Run {
  id: string
  compare_set_id: string
  run_date: string
  /** `REV-<YYYYMMDD>[-n]` -- the layer the clouds and badges were drawn on. */
  layer_name: string
  /** Absolute path of `<프로젝트>/출력/<run_date>[-n]/`. */
  output_dir: string
  scope: RunScope
  method: RunMethod
  /** Sheet pairs that produced a file, in output order. A pair with no
   * approved cluster is not exported and is not listed here. */
  pair_ids: string[]
  approved_count: number
  ignored_count: number
  files: RunOutputFile[]
  status: RunStatus
  error_message?: string | null
  created_at?: string
}

async function failure(res: Response, what: string): Promise<EngineHttpError> {
  const detail = await res.text().catch(() => '')
  return new EngineHttpError(res.status, `${what} failed (${String(res.status)}): ${detail}`)
}

export interface StartExportParams {
  runDate: string
}

export interface StartExportResult {
  jobId: string
  runId: string
}

/** `POST /compare/sets/{id}/export`. 409 (compare_set is not `compared`) and
 * every other non-2xx status surface as {@link EngineHttpError} -- unlike
 * `features/compare/api.ts`'s R1-04/R1-06 calls, this endpoint is expected to
 * exist by the time screen D can even be reached (R1-09 merges before
 * R1-10), so a 404 here is a real error, not a "not merged yet" signal. */
export async function startExport(compareSetId: string, params: StartExportParams): Promise<StartExportResult> {
  const path = `/api/v1/compare/sets/${encodeURIComponent(compareSetId)}/export`
  const res = await engineFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_date: params.runDate, scope: 'all', method: 'auto' }),
  })
  if (!res.ok) throw await failure(res, path)
  const dto = (await res.json()) as { job_id: string; run_id: string }
  return { jobId: dto.job_id, runId: dto.run_id }
}

/** `GET /compare/runs/{run_id}` -- the API shape (contract §7's table:
 * absolute `files[].path`, `created_at` present, `schema_version` absent). */
export async function getRun(runId: string): Promise<Run> {
  const path = `/api/v1/compare/runs/${encodeURIComponent(runId)}`
  const res = await engineFetch(path)
  if (!res.ok) throw await failure(res, path)
  return (await res.json()) as Run
}

/** `GET /compare/runs/{run_id}/tsv` -- `changes.tsv`'s bytes, decoded as the
 * UTF-8 text `docs/dev/compare-export.md` documents (no BOM, LF endings).
 * 409 until the run has written the file (mirrored here as an
 * {@link EngineHttpError}, same as every other non-2xx). */
export async function getRunTsv(runId: string): Promise<string> {
  const path = `/api/v1/compare/runs/${encodeURIComponent(runId)}/tsv`
  const res = await engineFetch(path)
  if (!res.ok) throw await failure(res, path)
  return res.text()
}
