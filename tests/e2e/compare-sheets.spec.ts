import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { hasTestHooks, launchHalo, REPO_ROOT, waitForStatus, type HaloElectronApp } from '../../packages/testing/src/electron'

/**
 * R1-05 e2e: screens A (세트 지정) and B (도곽 목록) driven through the real
 * rendered UI, against the real engine sidecar the harness spawns. Pattern
 * (manual `launchHalo()` instead of the `haloApp`/`window` fixtures, so
 * `HALO_E2E_PICK_FOLDERS` can be set on this process's env *before* the
 * child Electron process is spawned and inherits it) mirrors
 * `packages/testing/src/viewer.ts`'s `createViewerSession`.
 *
 * `fixtures/compare/S13_multi_sheet/{before,after}` (R1-07) each hold one
 * `plan.dxf` with two title blocks (A-101, A-102) -- DXF input needs no
 * ZWCAD/conversion step at all (`docs/dev/compare-ingest.md`: "DXF 입력은
 * 변환 없음"), so this spec runs identically on macOS and Windows CI. The
 * fixture directories themselves are never touched (CLAUDE.md rule 1) --
 * everything is copied into throwaway temp dirs first, so no `.halo/`
 * bundle is ever written under `fixtures/`.
 *
 * R1-04 (`POST .../frames`, `GET .../pairs`) may not be merged into the
 * branch this spec runs on yet. Rather than skip the whole file, it probes
 * `GET .../pairs` after the ingest job completes and branches: 200 runs
 * the full sheet-list assertions (rows, filter chips, `compareGetScreen()
 * === 'sheets'`), a 404 instead asserts the "준비 중" toast and that the
 * screen stays on A -- see this task's report "Follow-ups" for re-running
 * the 200 branch once R1-04 is merged.
 */

const FIXTURE_BEFORE = join(REPO_ROOT, 'fixtures/compare/S13_multi_sheet/before')
const FIXTURE_AFTER = join(REPO_ROOT, 'fixtures/compare/S13_multi_sheet/after')
const SCREENSHOT_DIR = join(REPO_ROOT, 'test-results/compare-sheets')

interface EngineConnection {
  baseUrl: string
  token: string
}

// `apps/web/src/api/halocad.d.ts`'s ambient `Window.halocad` isn't part of
// this package's own tsconfig "program" (same reasoning as
// `tests/e2e/xref.spec.ts`'s identical local redeclaration).
declare global {
  interface Window {
    halocad: { engine: { getConnection: () => Promise<EngineConnection> } }
  }
}

/**
 * `window.__haloTest`'s R1-05 hooks, called via inline casts inside each
 * `page.evaluate` rather than a `declare global` augmentation --
 * `packages/testing/src/electron.ts` (imported below) already declares a
 * narrower `Window.__haloTest` for `getStatus()` alone, and widening it
 * here would conflict with that declaration inside the same TS program.
 */
type Page = HaloElectronApp['window']

async function compareGetSummary(page: Page): Promise<{ id: string } | null> {
  return page.evaluate(
    () =>
      (window as unknown as { __haloTest: { compareGetSummary(): { id: string } | null } }).__haloTest.compareGetSummary(),
  )
}

async function compareGetScreen(page: Page): Promise<string> {
  return page.evaluate(
    () => (window as unknown as { __haloTest: { compareGetScreen(): string } }).__haloTest.compareGetScreen(),
  )
}

async function compareGoto(page: Page, target: string): Promise<void> {
  await page.evaluate(
    (screenName) => {
      ;(window as unknown as { __haloTest: { compareGoto(s: string): void } }).__haloTest.compareGoto(screenName)
    },
    target,
  )
}

function engineFetch(connection: EngineConnection, requestPath: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${connection.token}`)
  headers.set('Content-Type', 'application/json')
  return fetch(`${connection.baseUrl}${requestPath}`, { ...init, headers })
}

test.describe('compare screens A -> B (ingest, frames, sheet list)', () => {
  let app: HaloElectronApp | null = null
  let beforeDir: string | undefined
  let afterDir: string | undefined

  test.beforeAll(async () => {
    test.skip(
      !existsSync(FIXTURE_BEFORE) || !existsSync(FIXTURE_AFTER),
      'fixtures/compare/S13_multi_sheet가 없습니다 (R1-07 미병합)',
    )

    mkdirSync(SCREENSHOT_DIR, { recursive: true })
    beforeDir = mkdtempSync(join(tmpdir(), 'halo-e2e-compare-before-'))
    afterDir = mkdtempSync(join(tmpdir(), 'halo-e2e-compare-after-'))
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
    if (beforeDir) rmSync(beforeDir, { recursive: true, force: true })
    if (afterDir) rmSync(afterDir, { recursive: true, force: true })
  })

  test('picks both folders, ingests, shows the summary card, then frames', async () => {
    if (!app || !beforeDir || !afterDir) throw new Error('beforeAll did not complete (see its own skip reason)')
    const page = app.window

    const hooksPresent = await hasTestHooks(page)
    test.skip(!hooksPresent, 'window.__haloTest 훅이 없습니다 (HALO_E2E 꺼짐)')
    await waitForStatus(page, 'ready', 30_000)

    await expect(page.getByTestId('set-screen')).toBeVisible()

    // Screen A: the two "폴더 선택…" buttons, in DOM order (전 폴더 panel
    // first) -- HALO_E2E_PICK_FOLDERS is a FIFO, so click order fixes which
    // temp dir lands in beforeDir vs afterDir.
    const pickButtons = page.getByRole('button', { name: '폴더 선택…' })
    await pickButtons.nth(0).click()
    await expect(page.getByText(beforeDir)).toBeVisible()
    await pickButtons.nth(1).click()
    await expect(page.getByText(afterDir)).toBeVisible()

    await page.getByRole('button', { name: '인입 시작' }).click()

    // One DXF per side, no conversion needed -- comfortably under 30s even
    // on a slow CI runner.
    await expect(page.getByText('파일 1개').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('실패 0').first()).toBeVisible()
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-a-summary.png') })

    const connection = await page.evaluate(() => window.halocad.engine.getConnection())
    const summary = await compareGetSummary(page)
    if (!summary?.id) throw new Error('compareGetSummary() returned no id after ingest')
    const compareSetId = summary.id

    const pairsRes = await engineFetch(connection, `/api/v1/compare/sets/${compareSetId}/pairs`)

    if (pairsRes.status === 200) {
      // R1-04 is merged on this branch: the whole A -> B flow completes for
      // real, with real sheet rows.
      await expect.poll(() => compareGetScreen(page), { timeout: 30_000 }).toBe('sheets')

      const rows = page.locator('[data-testid="sheets-screen"] table tbody tr')
      await expect(rows.first()).toBeVisible()
      expect(await rows.count()).toBeGreaterThanOrEqual(1)

      await expect(page.getByRole('button', { name: /^전체/ })).toBeVisible()
      await page.getByRole('button', { name: /^변경/ }).click()
      await expect(rows.first()).toBeVisible()

      await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-b-sheets.png') })
      expect(await compareGetScreen(page)).toBe('sheets')
    } else {
      // R1-04 is not merged yet: `startFrames` 404s, screen A shows the
      // "준비 중" toast and stays put (brief "Defaults for ambiguity").
      expect(pairsRes.status).toBe(404)
      await expect(page.getByText('도곽 추출 기능이 아직 준비되지 않았습니다')).toBeVisible({ timeout: 30_000 })
      expect(await compareGetScreen(page)).toBe('set')

      // Screen B's own placeholder-vs-ready branch still renders correctly
      // even with no compare_set pairs yet -- captured here for the report
      // (both screens' screenshots) even though this run never reaches it
      // through the normal ingest -> frames -> sheets transition.
      await compareGoto(page, 'sheets')
      await expect(page.getByTestId('sheets-screen')).toBeVisible()
      await expect(page.getByText('도곽 짝 맞춤 기능이 아직 준비되지 않았습니다')).toBeVisible()
      await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-b-not-ready.png') })
    }
  })
})
