import { engineFetch } from '../../api/engine'
// `window.halocad`'s ambient type comes from ./api/halocad.d.ts, picked up
// automatically via tsconfig's "include": ["src"] -- no import needed (and
// a bare side-effect import of a pure .d.ts file breaks Vite's module
// resolution at test/dev-server runtime, unlike plain `tsc`).

/**
 * Engine client for `docs/contracts/wave-3.md` "W3-03 라우터 패턴" 아래
 * `engine/src/halo_engine/api/routers/xrefs.py`'s five endpoints (brief
 * W3-06 Files-you-own). Field names are converted between this module's
 * camelCase and the wire's snake_case at the boundary, the same pattern
 * every other feature's own `api.ts` client in this codebase follows.
 */

export type XrefLinkStatus = 'RESOLVED' | 'UNRESOLVED'

export interface XrefLink {
  blockName: string
  declaredPath: string
  resolvedPath: string | null
  status: XrefLinkStatus
}

interface XrefLinkDto {
  block_name: string
  declared_path: string
  resolved_path: string | null
  status: XrefLinkStatus
}

function fromDto(dto: XrefLinkDto): XrefLink {
  return {
    blockName: dto.block_name,
    declaredPath: dto.declared_path,
    resolvedPath: dto.resolved_path,
    status: dto.status,
  }
}

async function expectOk(res: Response, what: string): Promise<Response> {
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${what} failed (${String(res.status)}): ${detail}`)
  }
  return res
}

/** `GET /files/{id}/xrefs` -- the XREF tree for one host file. */
export async function getFileXrefs(fileId: string): Promise<XrefLink[]> {
  const res = await expectOk(
    await engineFetch(`/api/v1/files/${encodeURIComponent(fileId)}/xrefs`),
    'GET xrefs',
  )
  const dtos = (await res.json()) as XrefLinkDto[]
  return dtos.map(fromDto)
}

export interface ResolveXrefResult {
  jobId: string
  fileId: string
}

/** `POST /files/{id}/xrefs/{name}/resolve` -- manual file match for one block. */
export async function resolveFileXref(
  fileId: string,
  blockName: string,
  resolvedPath: string,
): Promise<ResolveXrefResult> {
  const res = await expectOk(
    await engineFetch(
      `/api/v1/files/${encodeURIComponent(fileId)}/xrefs/${encodeURIComponent(blockName)}/resolve`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved_path: resolvedPath }),
      },
    ),
    'resolve xref',
  )
  const dto = (await res.json()) as { job_id: string; file_id: string }
  return { jobId: dto.job_id, fileId: dto.file_id }
}

export interface SearchPathsUpdateResult {
  searchPaths: string[]
  jobIds: string[]
}

/** `PUT /projects/{id}/search-paths` -- the folder-pick dialog flow. */
export async function updateSearchPaths(
  projectId: string,
  searchPaths: string[],
  reimportFileIds: string[] = [],
): Promise<SearchPathsUpdateResult> {
  const res = await expectOk(
    await engineFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/search-paths`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ search_paths: searchPaths, reimport_file_ids: reimportFileIds }),
    }),
    'update search paths',
  )
  const dto = (await res.json()) as { search_paths: string[]; job_ids: string[] }
  return { searchPaths: dto.search_paths, jobIds: dto.job_ids }
}

export interface ImportSettings {
  searchPaths: string[]
  ignorePatterns: string[]
}

/** `GET /projects/{id}/import-settings` -- search paths + ignore patterns together. */
export async function getImportSettings(projectId: string): Promise<ImportSettings> {
  const res = await expectOk(
    await engineFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/import-settings`),
    'get import settings',
  )
  const dto = (await res.json()) as { search_paths: string[]; ignore_patterns: string[] }
  return { searchPaths: dto.search_paths, ignorePatterns: dto.ignore_patterns }
}

/** `PUT /projects/{id}/import-settings` -- the project settings panel's "단순 텍스트 목록". */
export async function updateImportSettings(
  projectId: string,
  settings: ImportSettings,
): Promise<ImportSettings> {
  const res = await expectOk(
    await engineFetch(`/api/v1/projects/${encodeURIComponent(projectId)}/import-settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        search_paths: settings.searchPaths,
        ignore_patterns: settings.ignorePatterns,
      }),
    }),
    'update import settings',
  )
  const dto = (await res.json()) as { search_paths: string[]; ignore_patterns: string[] }
  return { searchPaths: dto.search_paths, ignorePatterns: dto.ignore_patterns }
}

export type JobStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED' | 'CANCELLED'

/**
 * `GET /jobs/{id}`, polled while a folder-pick/manual-match re-import is in
 * flight. A WS-driven `job.progress`/`job.done` client belongs to
 * `apps/web/src/features/files/**`/`state/**` (out of this task's "Files
 * you own"); polling here keeps the xref dialog fully self-contained.
 */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
  const res = await expectOk(
    await engineFetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`),
    'get job',
  )
  const dto = (await res.json()) as { status: JobStatus }
  return dto.status
}

const TERMINAL_JOB_STATUSES = new Set<JobStatus>(['DONE', 'FAILED', 'CANCELLED'])

/** Polls `getJobStatus` until it reaches a terminal state or `timeoutMs` elapses. */
export async function waitForJob(jobId: string, timeoutMs = 60_000): Promise<JobStatus> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const status = await getJobStatus(jobId)
    if (TERMINAL_JOB_STATUSES.has(status) || Date.now() >= deadline) return status
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
}

/**
 * `window.halocad.files.pickDrawings()` reused as the "파일을 개별 매칭"
 * picker (brief Goal) -- the same native multi-select dialog W3-01 wires
 * for opening drawings, here used to pick exactly one XREF target file.
 */
export async function pickOneFile(): Promise<string | null> {
  const paths = await window.halocad.files.pickDrawings()
  return paths[0] ?? null
}
