import { mkdtempSync, copyFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { hasTestHooks, waitForStatus, REPO_ROOT } from '../../packages/testing/src/electron'

/**
 * W3-06 e2e: brief Constraints' scenario -- "F10 호스트를 F10_grid.dxf 없이
 * 임시 폴더에서 열면 다이얼로그가 뜨고, 폴더 지정 후 그리드가 보인다."
 *
 * `apps/web`'s app shell does not yet mount `features/xref`'s dialog
 * (`docs/dev/xref.md` "아직 앱 셸에 연결되지 않았다" -- that wiring belongs
 * to whichever task owns `App.tsx`/the dock components, outside this
 * task's "Files you own"), so this spec cannot drive the actual dialog
 * through the rendered UI yet. It still launches the real packaged app
 * (real engine sidecar included) and exercises the exact scenario the
 * brief describes against the engine directly -- reading
 * `window.halocad.engine.getConnection()` the same way the real dialog
 * will once it is wired (`docs/contracts/wave-2.md`'s IPC contract) --
 * which is the actual, engine-owned behaviour under test (brief
 * Constraints: "해석 순서는 엔진이 소유. UI는 검색 경로만 더한다").
 */

interface EngineConnection {
  baseUrl: string
  token: string
}

interface DrawingSetCreateResponse {
  job_id: string
  drawing_set_id: string
}

interface JobSummary {
  status: string
}

interface XrefLinkSummary {
  block_name: string
  declared_path: string
  resolved_path: string | null
  status: 'RESOLVED' | 'UNRESOLVED'
}

interface DrawingFileSummary {
  id: string
  original_name: string
  import_status: string
}

interface ProjectCreateResponse {
  id: string
}

interface SearchPathsUpdateResponse {
  job_ids: string[]
}

// `apps/web/src/api/halocad.d.ts`'s ambient `Window.halocad` isn't part of
// this package's own tsconfig "program" (apps/web is intentionally
// independent, same reasoning as `packages/testing/src/electron.ts`'s own
// local `Window.__haloTest` declaration) -- redeclared here for the one
// property this spec actually reads inside `window.evaluate()`.
declare global {
  interface Window {
    halocad: { engine: { getConnection: () => Promise<EngineConnection> } }
  }
}

const FIXTURES_GENERATED = path.join(REPO_ROOT, 'fixtures', 'generated')
const TERMINAL_JOB_STATUSES = new Set(['DONE', 'FAILED', 'CANCELLED'])

function engineFetch(connection: EngineConnection, requestPath: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${connection.token}`)
  headers.set('Content-Type', 'application/json')
  return fetch(`${connection.baseUrl}${requestPath}`, { ...init, headers })
}

async function waitForJob(connection: EngineConnection, jobId: string, timeoutMs = 60_000): Promise<JobSummary> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const res = await engineFetch(connection, `/api/v1/jobs/${jobId}`)
    const job = (await res.json()) as JobSummary
    if (TERMINAL_JOB_STATUSES.has(job.status) || Date.now() >= deadline) return job
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
}

test.describe('W3-06 XREF resolution (engine-level)', () => {
  test('an F10 host imported without its XREF target is unresolved, then resolves once the folder is added as a search path', async ({
    // Renamed to `page` at destructure time -- `packages/testing/src/electron.ts`'s
    // own `waitForStatus` comment explains why: naming it `window` would
    // shadow the bare `window` identifier inside `page.evaluate()`'s
    // callback (which must resolve to the *browser's* global, not this
    // Playwright `Page` value).
    window: page,
  }) => {
    const hooksPresent = await hasTestHooks(page)
    test.skip(!hooksPresent, 'window.__haloTest 훅이 없습니다 (HALO_E2E 꺼짐) -- 엔진 상태 단언을 건너뜁니다.')
    await waitForStatus(page, 'ready', 30_000)

    const connection = await page.evaluate(() => window.halocad.engine.getConnection())

    // Isolated temp folder with *only* the host DXF -- no F10_grid.dxf
    // sibling (brief: "F10_grid.dxf 없이 임시 폴더에서 열면").
    const isolatedDir = mkdtempSync(path.join(tmpdir(), 'halo-e2e-xref-'))
    const hostPath = path.join(isolatedDir, 'F10_host.dxf')
    copyFileSync(path.join(FIXTURES_GENERATED, 'F10_host.dxf'), hostPath)

    try {
      const projectDir = mkdtempSync(path.join(tmpdir(), 'halo-e2e-xref-project-'))
      const createProjectRes = await engineFetch(connection, '/api/v1/projects', {
        method: 'POST',
        body: JSON.stringify({ name: 'xref-e2e', path: path.join(projectDir, 'xref-e2e.halo') }),
      })
      expect(createProjectRes.status).toBe(201)
      const project = (await createProjectRes.json()) as ProjectCreateResponse

      // "열면" -- import with no search paths, so F10_grid.dxf cannot be found.
      const importRes = await engineFetch(connection, `/api/v1/projects/${project.id}/drawing-sets`, {
        method: 'POST',
        body: JSON.stringify({ files: [hostPath], search_paths: [] }),
      })
      expect(importRes.status).toBe(202)
      const created = (await importRes.json()) as DrawingSetCreateResponse
      const firstJob = await waitForJob(connection, created.job_id)
      expect(firstJob.status).toBe('DONE')

      const filesRes = await engineFetch(connection, `/api/v1/drawing-sets/${created.drawing_set_id}/files`)
      const files = (await filesRes.json()) as DrawingFileSummary[]
      expect(files).toHaveLength(1)
      const hostRow = files[0]
      if (!hostRow) throw new Error('expected exactly one imported file')
      expect(hostRow.import_status).toBe('DONE') // one unresolved xref does not fail the host

      // "다이얼로그가 뜨고" -- the engine-owned signal the dialog reads.
      const linksBeforeRes = await engineFetch(connection, `/api/v1/files/${hostRow.id}/xrefs`)
      const linksBefore = (await linksBeforeRes.json()) as XrefLinkSummary[]
      expect(linksBefore).toHaveLength(1)
      const [linkBefore] = linksBefore
      if (!linkBefore) throw new Error('expected exactly one xref link')
      expect(linkBefore.block_name).toBe('F10_GRID')
      expect(linkBefore.status).toBe('UNRESOLVED')

      // "폴더 지정 후" -- add fixtures/generated (where F10_grid.dxf actually
      // lives) as a search path and re-import this one host.
      const searchPathsRes = await engineFetch(connection, `/api/v1/projects/${project.id}/search-paths`, {
        method: 'PUT',
        body: JSON.stringify({ search_paths: [FIXTURES_GENERATED], reimport_file_ids: [hostRow.id] }),
      })
      expect(searchPathsRes.status).toBe(200)
      const searchPathsBody = (await searchPathsRes.json()) as SearchPathsUpdateResponse
      expect(searchPathsBody.job_ids).toHaveLength(1)
      const [reimportJobId] = searchPathsBody.job_ids
      if (!reimportJobId) throw new Error('expected one re-import job id')
      const secondJob = await waitForJob(connection, reimportJobId)
      expect(secondJob.status).toBe('DONE')

      // "그리드가 보인다" -- the grid's LINE/INSERT content is embedded and
      // resolvable; the F10_GRID block is what the viewer would render.
      const linksAfterRes = await engineFetch(connection, `/api/v1/files/${hostRow.id}/xrefs`)
      const linksAfter = (await linksAfterRes.json()) as XrefLinkSummary[]
      const [linkAfter] = linksAfter
      if (!linkAfter) throw new Error('expected exactly one xref link')
      expect(linkAfter.status).toBe('RESOLVED')
      expect(linkAfter.resolved_path).toBe(path.join(FIXTURES_GENERATED, 'F10_grid.dxf'))
    } finally {
      rmSync(isolatedDir, { recursive: true, force: true })
    }
  })
})
