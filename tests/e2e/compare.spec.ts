import { createHash } from 'node:crypto'
import { cpSync, existsSync, mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { hasTestHooks, launchHalo, REPO_ROOT, waitForStatus, type HaloElectronApp } from '../../packages/testing/src/electron'

/**
 * R1-10 e2e: Seed AC4's vertical slice, screens A -> D, tied into one spec --
 * 세트 지정 → 도곽 목록 → 검토(승인·무시) → 전체 도곽 출력 -- against the real
 * Electron app and the real engine sidecar. `tests/e2e/compare-sheets.spec.ts`
 * (R1-05, screens A/B) and `tests/e2e/compare-review.spec.ts` (R1-08, screen
 * C) each already prove their own screen in isolation; this spec proves the
 * hand-off between all four actually works end to end, plus screen D's own
 * export/result/폴더 열기/TSV behaviour (R1-09/R1-10).
 *
 * `fixtures/compare/S13_multi_sheet/{before,after}` (R1-07): one `plan.dxf`
 * per side with two title blocks -- A-101 unchanged, A-102 with two clusters
 * (a new wall, a new door; `truth.json`: `expected_cluster_count: 2`). DXF in,
 * DXF out -- no ZWCAD/conversion step, so this spec runs the same on macOS
 * and on Windows CI. Both fixture sides are copied into one throwaway project
 * folder first (CLAUDE.md rule 1: the fixture directory itself is never
 * written to -- no `.halo`, no `출력/`), and the two copies are siblings under
 * that folder so the engine's own `project_dir` resolution (contract §1:
 * "전·후 세트 폴더의 공통 부모") lands the output where this spec expects it,
 * `<project>/출력/2026-09-04`.
 *
 * This machine has no ZWCAD (macOS dev/CI, and the shared GitHub Actions
 * `windows-latest` runner has none installed either), so the export always
 * falls back to the `dxf-only` writer (`docs/dev/compare-export.md`'s "DWG
 * 저장 경로 선택" table) -- the spec asserts that fallback explicitly instead
 * of assuming a `.dwg` came out. Exercising the `zwcad-com` writer needs a
 * Windows install with ZWCAD 2026 running (see this task's report "Questions
 * for gate").
 */

const FIXTURE_BEFORE = join(REPO_ROOT, 'fixtures/compare/S13_multi_sheet/before')
const FIXTURE_AFTER = join(REPO_ROOT, 'fixtures/compare/S13_multi_sheet/after')
const SCREENSHOT_DIR = join(REPO_ROOT, 'test-results/compare')
/** Pinned, like every other run date in the suite (contract §11). */
const RUN_DATE = '2026-09-04'
const REV_LAYER = 'REV-20260904'

type Page = HaloElectronApp['window']

interface EngineConnection {
  baseUrl: string
  token: string
}

interface SidecarView {
  pair_id: string
  layer: string
  counts: { clusters: number; changes: number; minor: number; approved: number; ignored: number }
}

interface FrameView {
  sheet_no: string | null
}

interface PairView {
  id: string
  status: string
  cluster_count: number
  compare_dxf_path: string | null
  before_frame?: FrameView | null
  after_frame?: FrameView | null
}

interface RunOutputFileView {
  pair_id: string
  sheet_no: string | null
  path: string
  format: string
  writer: string
}

interface RunView {
  id: string
  compare_set_id: string
  run_date: string
  layer_name: string
  output_dir: string
  scope: string
  method: string
  pair_ids: string[]
  approved_count: number
  ignored_count: number
  files: RunOutputFileView[]
  status: string
}

/**
 * `window.__haloTest` reached through inline casts, like
 * `tests/e2e/compare-sheets.spec.ts` and `tests/e2e/compare-review.spec.ts`:
 * `packages/testing/src/electron.ts` declares a narrower `Window.__haloTest`
 * for `getStatus()` alone, and widening it here would clash inside the same
 * TS program.
 */
async function compareGetScreen(page: Page): Promise<string> {
  return page.evaluate(
    () => (window as unknown as { __haloTest: { compareGetScreen(): string } }).__haloTest.compareGetScreen(),
  )
}

async function compareGetPairs(page: Page): Promise<PairView[]> {
  return page.evaluate(
    () => (window as unknown as { __haloTest: { compareGetPairs(): PairView[] } }).__haloTest.compareGetPairs() as never,
  )
}

async function compareOpenPair(page: Page, pairId: string): Promise<void> {
  await page.evaluate(
    (id) =>
      (window as unknown as { __haloTest: { compareOpenPair(p: string): Promise<void> } }).__haloTest.compareOpenPair(id),
    pairId,
  )
}

async function compareGetClusters(page: Page): Promise<SidecarView | null> {
  return page.evaluate(
    () =>
      (
        window as unknown as { __haloTest: { compareGetClusters(): SidecarView | null } }
      ).__haloTest.compareGetClusters() as never,
  )
}

/** R1-10's own hook: the last finished export's `Run`, read back without
 * triggering a second export (that action is `compareRunExport`, exercised
 * for real by this spec's "출력 실행" button click below instead -- both
 * paths call the identical `state/export.ts::runExport`, and calling the hook
 * *as well* here would start a second, `-2`-suffixed export and break the
 * "output_dir ends with 출력/2026-09-04" assertion; see the task report's
 * "Decisions"). */
async function compareGetLastRun(page: Page): Promise<RunView | null> {
  return page.evaluate(
    () => (window as unknown as { __haloTest: { compareGetLastRun(): RunView | null } }).__haloTest.compareGetLastRun() as never,
  )
}

function engineFetch(connection: EngineConnection, requestPath: string): Promise<Response> {
  return fetch(`${connection.baseUrl}${requestPath}`, {
    headers: { Authorization: `Bearer ${connection.token}`, 'Content-Type': 'application/json' },
  })
}

/** sha256 of every regular file directly under `dir`, keyed by file name --
 * S13's fixture sides are flat (one `plan.dxf` each). Content, not mtime, so
 * `cpSync`'s own timestamp handling cannot produce a false "changed". */
function fileHashes(dir: string): Record<string, string> {
  const hashes: Record<string, string> = {}
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isFile()) hashes[name] = createHash('sha256').update(readFileSync(full)).digest('hex')
  }
  return hashes
}

test.describe('compare vertical slice (Seed AC4): 세트 지정 → 도곽 목록 → 검토 → 전체 도곽 출력', () => {
  let app: HaloElectronApp | null = null
  let projectDir: string | undefined
  let beforeDir: string | undefined
  let afterDir: string | undefined

  test.beforeAll(async () => {
    test.skip(
      !existsSync(FIXTURE_BEFORE) || !existsSync(FIXTURE_AFTER),
      'fixtures/compare/S13_multi_sheet가 없습니다 (R1-07 미병합)',
    )

    mkdirSync(SCREENSHOT_DIR, { recursive: true })

    // One project folder, 전/후 as siblings -- so the engine resolves
    // `project_dir` to this folder and `출력/2026-09-04` lands directly under
    // it (contract §1's "공통 부모" rule), and one `rmSync` on teardown
    // removes the copies, the `.halo` bundle and the output folder together.
    projectDir = mkdtempSync(join(tmpdir(), 'halo-e2e-compare-slice-'))
    beforeDir = join(projectDir, 'before')
    afterDir = join(projectDir, 'after')
    cpSync(FIXTURE_BEFORE, beforeDir, { recursive: true })
    cpSync(FIXTURE_AFTER, afterDir, { recursive: true })

    // Read by `apps/desktop/src/main/ipc.ts::pickFolder`'s e2e substitute --
    // must be set before `launchHalo()` spawns the child process, which
    // copies `process.env` at spawn time (contract §8's FIFO: one entry
    // consumed per `halocad:dialog:pick-folder` call, 전 then 후).
    process.env.HALO_E2E_PICK_FOLDERS = [beforeDir, afterDir].join(',')
    app = await launchHalo()
  })

  test.afterAll(async () => {
    await app?.close()
    delete process.env.HALO_E2E_PICK_FOLDERS
    if (projectDir) rmSync(projectDir, { recursive: true, force: true })
  })

  test('전체 슬라이스: 인입 → 도곽 목록 → 검토(승인·무시) → 출력', async () => {
    test.setTimeout(240_000)
    if (!app || !beforeDir || !afterDir) throw new Error('beforeAll did not complete (see its own skip reason)')
    const page = app.window

    const hooksPresent = await hasTestHooks(page)
    test.skip(!hooksPresent, 'window.__haloTest 훅이 없습니다 (HALO_E2E 꺼짐)')
    await waitForStatus(page, 'ready', 30_000)

    const connection = await page.evaluate(() =>
      (
        window as unknown as { halocad: { engine: { getConnection: () => Promise<EngineConnection> } } }
      ).halocad.engine.getConnection(),
    )

    // Baseline hashes of both source folders, taken before anything touches
    // them, so the very last assertion can prove they never changed
    // (CLAUDE.md rule 1; `docs/dev/compare-export.md` "쓰기 허용 경로").
    const beforeHashesBefore = fileHashes(beforeDir)
    const afterHashesBefore = fileHashes(afterDir)

    // ---------------------------------------------------------------- 화면 A
    await expect(page.getByTestId('set-screen')).toBeVisible()

    const pickButtons = page.getByRole('button', { name: '폴더 선택…' })
    await pickButtons.nth(0).click()
    await expect(page.getByText(beforeDir)).toBeVisible()
    await pickButtons.nth(1).click()
    await expect(page.getByText(afterDir)).toBeVisible()

    const runDateInput = page.locator('#compare-run-date')
    await runDateInput.fill(RUN_DATE)
    await expect(runDateInput).toHaveValue(RUN_DATE)

    await page.getByRole('button', { name: '인입 시작' }).click()
    // Two DXFs, no conversion needed -- well under 30s even on a slow runner.
    await expect(page.getByText('파일 1개').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('실패 0').first()).toBeVisible()
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-a-set.png') })

    // ---------------------------------------------------------------- 화면 B
    await expect.poll(() => compareGetScreen(page), { timeout: 30_000 }).toBe('sheets')
    await expect(page.getByTestId('sheets-screen')).toBeVisible()

    // Right after `POST .../frames`, pairs are matched but not yet compared
    // (status `pending` -- `same`/`changed` only exist once `POST .../run`
    // has actually diffed each pair), so only identity is checked here.
    const pairsAfterFrames = await compareGetPairs(page)
    const a101 = pairsAfterFrames.find((pair) => (pair.before_frame?.sheet_no ?? pair.after_frame?.sheet_no) === 'A-101')
    const a102 = pairsAfterFrames.find((pair) => (pair.before_frame?.sheet_no ?? pair.after_frame?.sheet_no) === 'A-102')
    if (!a101 || !a102) throw new Error('S13_multi_sheet은 A-101/A-102 두 도곽을 낸다')

    // 비교 실행. 화면은 계속 'sheets'에 머무르므로(비교 잡은 화면을 옮기지
    // 않는다), 짝의 `compare_dxf_path`가 채워지는 것으로 잡 완료를 확인한다.
    await page.getByRole('button', { name: '비교 실행' }).click()
    await expect
      .poll(
        async () => (await compareGetPairs(page)).find((pair) => pair.id === a102.id)?.compare_dxf_path ?? null,
        { timeout: 60_000 },
      )
      .not.toBeNull()
    const comparedPairs = await compareGetPairs(page)
    const comparedA101 = comparedPairs.find((pair) => pair.id === a101.id)
    const comparedA102 = comparedPairs.find((pair) => pair.id === a102.id)
    // truth.json: A-101 has no planted change, A-102 has two (a wall, a door).
    expect(comparedA101?.status).toBe('same')
    expect(comparedA102?.status).toBe('changed')
    expect(comparedA102?.cluster_count).toBe(2)
    // Row 2 (A-102) now shows 변경 and row 1 (A-101) shows 동일 -- the brief's
    // "화면 B 행 2(A-101 동일·A-102 변경)".
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-b-sheets.png') })

    // ---------------------------------------------------------------- 화면 C
    await compareOpenPair(page, a102.id)
    await expect(page.getByTestId('review-screen')).toBeVisible()
    const sidecar = await compareGetClusters(page)
    expect(sidecar?.counts.clusters).toBe(2)
    expect(sidecar?.layer).toBe(REV_LAYER)
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-review.png') })

    await page.getByTestId('cluster-approve-1').click()
    await expect(page.getByTestId('cluster-decision-1')).toHaveText('승인')
    await page.getByTestId('cluster-ignore-2').click()
    await expect(page.getByTestId('cluster-decision-2')).toHaveText('무시')

    const reloaded = await engineFetch(connection, `/api/v1/compare/pairs/${a102.id}/clusters`)
    expect(reloaded.status).toBe(200)
    const reloadedSidecar = (await reloaded.json()) as SidecarView
    expect(reloadedSidecar.counts.approved).toBe(1)
    expect(reloadedSidecar.counts.ignored).toBe(1)

    // ---------------------------------------------------------------- 화면 D
    await page.getByRole('button', { name: '도곽 목록으로' }).click()
    await expect(page.getByTestId('sheets-screen')).toBeVisible()
    await page.getByRole('button', { name: '전체 도곽 출력…' }).click()
    await expect(page.getByTestId('export-screen')).toBeVisible()
    expect(await compareGetScreen(page)).toBe('export')

    await expect(page.getByText('전체 도곽')).toBeVisible()
    await expect(page.getByText(/승인 1건 · 무시 1건 · 대상 도곽 1장/)).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '출력 실행' }).click()
    await expect(page.getByTestId('export-result')).toBeVisible({ timeout: 60_000 })
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-d-export.png') })

    const run = await compareGetLastRun(page)
    if (!run) throw new Error('compareGetLastRun() returned null after the export finished')
    expect(run.status).toBe('done')
    expect(run.pair_ids).toEqual([a102.id])
    expect(run.files).toHaveLength(1)
    const file = run.files[0]
    if (!file) throw new Error('run.files[0] is missing')
    expect(file.sheet_no).toBe('A-102')
    // No ZWCAD on this machine -- the export falls back to a DXF copy.
    expect(file.writer).toBe('dxf-only')
    expect(file.format).toBe('dxf')
    expect(run.output_dir.endsWith(join('출력', RUN_DATE))).toBe(true)
    expect(run.layer_name).toBe(REV_LAYER)

    // 마크업 파일이 실제로 있고 REV 레이어 이름을 담고 있다 (dxf-only라 그냥 텍스트로 읽힌다).
    expect(existsSync(file.path)).toBe(true)
    const markupText = readFileSync(file.path, 'utf-8')
    expect(markupText).toContain(REV_LAYER)

    // changes.tsv: 승인 1행 + 무시 1행 (대기는 없다 -- S13의 클러스터는 이
    // 둘뿐이다).
    const tsvPath = join(run.output_dir, 'changes.tsv')
    expect(existsSync(tsvPath)).toBe(true)
    const tsvLines = readFileSync(tsvPath, 'utf-8').replace(/\n$/, '').split('\n')
    expect(tsvLines[0]?.split('\t')).toEqual(['도면번호', '도면명', '번호', '종류', '내용', '판정', '일자'])
    expect(tsvLines).toHaveLength(3)
    const decisions = tsvLines.slice(1).map((line) => line.split('\t')[5]).sort()
    expect(decisions).toEqual(['무시', '승인'])

    // 원본 폴더는 그대로다 (CLAUDE.md 규칙 1) -- 인입·비교·출력을 다 거친 뒤에도.
    expect(fileHashes(beforeDir)).toEqual(beforeHashesBefore)
    expect(fileHashes(afterDir)).toEqual(afterHashesBefore)

    // "폴더 열기": 이 harness가 주는 유일한 노출 통로인 메인 프로세스
    // `process.env`를 통해 기록을 확인한다 (`apps/desktop/src/main/ipc.ts`의
    // `openPath`/`recordE2EOpenedPath`, `docs/contracts/r1.md` §8).
    await page.getByRole('button', { name: '폴더 열기' }).click()
    const opened = await app.app.evaluate(() => process.env.HALO_E2E_OPENED_PATHS)
    expect(opened?.split(',')).toContain(run.output_dir)

    // "변경 리스트 TSV 복사": 성공 토스트가 뜬다 (2초 후 사라지는 것은 UI
    // 세부사항이라 `state/export.test.ts`에서 이미 가짜 타이머로 확인했다).
    await page.getByRole('button', { name: '변경 리스트 TSV 복사' }).click()
    await expect(page.getByText('TSV를 클립보드에 복사했습니다')).toBeVisible()
  })
})
