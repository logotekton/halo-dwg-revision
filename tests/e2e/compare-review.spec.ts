import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { hasTestHooks, launchHalo, REPO_ROOT, waitForStatus, type HaloElectronApp } from '../../packages/testing/src/electron'

/**
 * R1-08 e2e: screen C (검토) end to end -- the real Electron app, the real
 * engine sidecar, the real mlightcad viewer drawing a real compare DXF.
 *
 * `fixtures/compare/S02_move_door` (R1-07) is one sheet (A-101) whose door
 * INSERT moved 1,250mm east: exactly one cluster, which is what the fixture's
 * `truth.json` pins. DXF in, DXF out -- no conversion step, so this spec runs
 * the same on macOS and on Windows CI. The fixture directories themselves are
 * never touched (CLAUDE.md rule 1): both sides are copied into throwaway temp
 * dirs, and the `.halo` bundle lands next to those copies.
 *
 * The last test switches to `S05_added` in the same app, because S02 cannot
 * show that a view mode reaches the *picture*: its only compare entity is an
 * INSERT, and this viewer resolves visibility per drawn entity, so a door
 * whose geometry lives on `A-DOOR` inside the block definition keeps drawing
 * even with `__CMP_ADDED` off (see the task report). S05's added wall is a
 * plain LWPOLYLINE on `__CMP_ADDED`, so hiding that layer really does repaint.
 *
 * The tests share one app on purpose (serial): comparing a set takes an
 * ingest, a frames and a compare job, and every later assertion is about the
 * sheet that flow opened.
 */

const FIXTURES = join(REPO_ROOT, 'fixtures/compare')
const MOVED_DOOR = join(FIXTURES, 'S02_move_door')
const ADDED = join(FIXTURES, 'S05_added')
const MULTI_SHEET = join(FIXTURES, 'S13_multi_sheet')
const SCREENSHOT_DIR = join(REPO_ROOT, 'test-results/compare-review')
/** Pinned, like every other run date in the suite (contract §11). */
const RUN_DATE = '2026-09-04'
const REV_LAYER = 'REV-20260904'

type Page = HaloElectronApp['window']

interface EngineConnection {
  baseUrl: string
  token: string
}

interface ClusterView {
  id: string
  number: number
  kind: string
  decision: string
  label: string
  user_label: string | null
}

interface ChangeView {
  id: string
  etype: string
  minor: boolean
  cluster_id: string | null
}

interface Sidecar {
  pair_id: string
  layer: string
  clusters: ClusterView[]
  changes: ChangeView[]
  counts: { clusters: number; changes: number; minor: number; approved: number; ignored: number }
}

interface PairView {
  id: string
  cluster_count: number
  compare_dxf_path: string | null
}

/**
 * `window.__haloTest` reached through inline casts, like
 * `tests/e2e/compare-sheets.spec.ts`: `packages/testing/src/electron.ts`
 * declares a narrower `Window.__haloTest` for `getStatus()` and widening it
 * here would clash inside the same TS program.
 */
async function compareStartSet(page: Page, dirs: { beforeDir: string; afterDir: string }): Promise<string> {
  return page.evaluate(
    (params) =>
      (
        window as unknown as {
          __haloTest: {
            compareStartSet(p: { beforeDir: string; afterDir: string; runDate: string }): Promise<string>
          }
        }
      ).__haloTest.compareStartSet(params),
    { ...dirs, runDate: RUN_DATE },
  )
}

async function compareRunCompare(page: Page): Promise<void> {
  await page.evaluate(() =>
    (window as unknown as { __haloTest: { compareRunCompare(): Promise<void> } }).__haloTest.compareRunCompare(),
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

async function compareGetClusters(page: Page): Promise<Sidecar | null> {
  return page.evaluate(
    () =>
      (
        window as unknown as { __haloTest: { compareGetClusters(): Sidecar | null } }
      ).__haloTest.compareGetClusters() as never,
  )
}

function engineFetch(connection: EngineConnection, requestPath: string): Promise<Response> {
  return fetch(`${connection.baseUrl}${requestPath}`, {
    headers: { Authorization: `Bearer ${connection.token}`, 'Content-Type': 'application/json' },
  })
}

/** The compare canvas as base64 PNG -- two shots that differ mean the camera
 * (or the layer set) actually changed, the same signal
 * `tests/e2e/viewer.spec.ts` uses for layer visibility. */
async function canvasShot(page: Page): Promise<string> {
  const shot = await page.getByTestId('review-canvas').screenshot()
  return shot.toString('base64')
}

/** The compare layers the *host* reports as drawing, published by screen C on
 * the canvas container after every mode change (so this reads `layers()`, not
 * the store's intention). */
async function visibleLayers(page: Page): Promise<string[]> {
  const value = await page.getByTestId('review-canvas').getAttribute('data-cmp-visible')
  return value ? value.split(',') : []
}

/** Copies one fixture side into a throwaway directory (CLAUDE.md rule 1). */
function copyFixture(dir: string, prefix: string): string {
  const target = mkdtempSync(join(tmpdir(), prefix))
  cpSync(dir, target, { recursive: true })
  return target
}

async function compareAndOpenFirstPair(page: Page, dirs: { beforeDir: string; afterDir: string }): Promise<string> {
  await compareStartSet(page, dirs)
  await compareRunCompare(page)
  const compared = (await compareGetPairs(page)).filter((pair) => pair.compare_dxf_path !== null)
  const first = compared[0]
  if (!first) throw new Error('no compared sheet pair')
  await compareOpenPair(page, first.id)
  return first.id
}

test.describe.configure({ mode: 'serial' })

test.describe('compare screen C (검토)', () => {
  let app: HaloElectronApp | null = null
  const temps: string[] = []
  let pairId: string | null = null
  let connection: EngineConnection | null = null

  test.beforeAll(async () => {
    test.skip(
      !existsSync(MOVED_DOOR) || !existsSync(ADDED) || !existsSync(MULTI_SHEET),
      'fixtures/compare가 없습니다 (R1-07 미병합)',
    )
    mkdirSync(SCREENSHOT_DIR, { recursive: true })
    app = await launchHalo()
  })

  test.afterAll(async () => {
    await app?.close()
    for (const dir of temps) rmSync(dir, { recursive: true, force: true })
  })

  test('compares S02_move_door and opens it in 검토 with one cluster', async () => {
    test.setTimeout(180_000)
    if (!app) throw new Error('beforeAll did not complete (see its own skip reason)')
    const page = app.window

    test.skip(!(await hasTestHooks(page)), 'window.__haloTest 훅이 없습니다 (HALO_E2E 꺼짐)')
    await waitForStatus(page, 'ready', 30_000)

    connection = await page.evaluate(() =>
      (
        window as unknown as { halocad: { engine: { getConnection: () => Promise<EngineConnection> } } }
      ).halocad.engine.getConnection(),
    )

    const beforeDir = copyFixture(join(MOVED_DOOR, 'before'), 'halo-e2e-review-s02-before-')
    const afterDir = copyFixture(join(MOVED_DOOR, 'after'), 'halo-e2e-review-s02-after-')
    temps.push(beforeDir, afterDir)
    pairId = await compareAndOpenFirstPair(page, { beforeDir, afterDir })

    await expect(page.getByTestId('review-screen')).toBeVisible()
    const sidecar = await compareGetClusters(page)
    // truth.json: expected_cluster_count 1 (door D1 moved 1,250mm east).
    expect(sidecar?.counts.clusters).toBe(1)
    expect(sidecar?.layer).toBe(REV_LAYER)
    await expect(page.getByTestId('cluster-row-1')).toBeVisible()
    await expect(page.getByTestId('cluster-decision-1')).toHaveText('대기')

    // The drawing is open and painted, and the host reports the overlay set.
    expect(await visibleLayers(page)).toEqual(['__CMP_ADDED', '__CMP_REMOVED', REV_LAYER])
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-overlay.png') })
  })

  test('the number badge moves the camera to that cluster', async () => {
    if (!app) throw new Error('the first test did not complete')
    const page = app.window

    // Move the camera away first with the wheel, so "the canvas changed" after
    // the click cannot be satisfied by a view that was already framing the
    // cluster.
    const opened = await canvasShot(page)
    const box = await page.getByTestId('review-canvas').boundingBox()
    if (!box) throw new Error('the compare canvas has no box')
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.wheel(0, 600)
    await expect.poll(() => canvasShot(page).then((shot) => shot !== opened), { timeout: 20_000 }).toBe(true)
    const zoomedOut = await canvasShot(page)

    await page.getByTestId('cluster-number-1').click()

    // `zoomTo` only marks the view dirty; the camera reaches the canvas on a
    // later animation frame, so this is polled rather than read once.
    await expect.poll(() => canvasShot(page).then((shot) => shot !== zoomedOut), { timeout: 20_000 }).toBe(true)
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-zoomed.png') })
  })

  test('승인 is stored on the engine, not only in the screen', async () => {
    if (!app || !connection || !pairId) throw new Error('the first test did not complete')
    const page = app.window

    await page.getByTestId('cluster-approve-1').click()
    await expect(page.getByTestId('cluster-decision-1')).toHaveText('승인')

    const res = await engineFetch(connection, `/api/v1/compare/pairs/${pairId}/clusters`)
    expect(res.status).toBe(200)
    const reloaded = (await res.json()) as Sidecar
    expect(reloaded.clusters[0]?.decision).toBe('approved')
    expect(reloaded.counts.approved).toBe(1)
  })

  test('보기 모드 "전" turns __CMP_ADDED off in the host layer table', async () => {
    if (!app) throw new Error('the first test did not complete')
    const page = app.window

    await page.locator('button[data-mode="before"]').click()
    await expect.poll(() => visibleLayers(page), { timeout: 20_000 }).toEqual(['__CMP_REMOVED', REV_LAYER])

    await page.locator('button[data-mode="after"]').click()
    await expect.poll(() => visibleLayers(page), { timeout: 20_000 }).toEqual(['__CMP_ADDED', REV_LAYER])

    await page.locator('button[data-mode="before"]').click()
    await expect.poll(() => visibleLayers(page), { timeout: 20_000 }).toEqual(['__CMP_REMOVED', REV_LAYER])
    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-before-mode.png') })
  })

  test('a view mode repaints the canvas (S05_added, whose change is not a block)', async () => {
    test.setTimeout(180_000)
    if (!app) throw new Error('the first test did not complete')
    const page = app.window

    const beforeDir = copyFixture(join(ADDED, 'before'), 'halo-e2e-review-s05-before-')
    const afterDir = copyFixture(join(ADDED, 'after'), 'halo-e2e-review-s05-after-')
    temps.push(beforeDir, afterDir)
    await compareAndOpenFirstPair(page, { beforeDir, afterDir })

    const sidecar = await compareGetClusters(page)
    // truth.json: a new wall LWPOLYLINE and a new door INSERT, far enough
    // apart to be two clouds.
    expect(sidecar?.counts.clusters).toBe(2)

    // The wall, not the door: the door is an INSERT and its geometry is inside
    // the block definition, on `A-DOOR`, which this viewer keeps drawing when
    // the INSERT's own layer is off.
    const wall = sidecar?.changes.find((change) => change.etype === 'LWPOLYLINE' && !change.minor)
    const wallCluster = sidecar?.clusters.find((cluster) => cluster.id === wall?.cluster_id)
    if (!wallCluster) throw new Error('S05_added has no LWPOLYLINE cluster')

    await page.locator('button[data-mode="overlay"]').click()
    await expect.poll(() => visibleLayers(page), { timeout: 20_000 }).toEqual([
      '__CMP_ADDED',
      '__CMP_REMOVED',
      REV_LAYER,
    ])
    await page.getByTestId(`cluster-number-${String(wallCluster.number)}`).click()
    await page.waitForTimeout(1_000)
    const overlayShot = await canvasShot(page)

    await page.locator('button[data-mode="before"]').click()
    await expect.poll(() => visibleLayers(page), { timeout: 20_000 }).toEqual(['__CMP_REMOVED', REV_LAYER])
    // The canvas really repaints, which also proves this second sheet is drawn
    // at all: a blank canvas would compare equal to itself in both modes.
    await expect.poll(() => canvasShot(page).then((shot) => shot !== overlayShot), { timeout: 20_000 }).toBe(true)

    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-added-before-mode.png') })
  })

  test('다음 도곽 opens the next sheet in the list without leaving 검토', async () => {
    test.setTimeout(180_000)
    if (!app) throw new Error('the first test did not complete')
    const page = app.window

    // S13_multi_sheet: one file, two title blocks -- A-101 unchanged (no cloud
    // marks) and A-102 with two. Walking from the first to the second is the
    // path that closes one drawing and opens another inside one mount.
    const beforeDir = copyFixture(join(MULTI_SHEET, 'before'), 'halo-e2e-review-s13-before-')
    const afterDir = copyFixture(join(MULTI_SHEET, 'after'), 'halo-e2e-review-s13-after-')
    temps.push(beforeDir, afterDir)
    await compareAndOpenFirstPair(page, { beforeDir, afterDir })

    await expect(page.getByText('이 도곽에는 클라우드 마크가 없습니다')).toBeVisible()
    const firstSheet = await canvasShot(page)

    await page.getByRole('button', { name: '다음 도곽' }).click()
    await expect
      .poll(() => compareGetClusters(page).then((sidecar) => sidecar?.counts.clusters ?? -1), { timeout: 60_000 })
      .toBe(2)
    await expect.poll(() => canvasShot(page).then((shot) => shot !== firstSheet), { timeout: 20_000 }).toBe(true)

    // Wheel-zoom the second sheet: a canvas that is actually drawing changes
    // when the camera does, and a blank one cannot.
    const box = await page.getByTestId('review-canvas').boundingBox()
    if (!box) throw new Error('the compare canvas has no box')
    const framed = await canvasShot(page)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.wheel(0, 600)
    await expect.poll(() => canvasShot(page).then((shot) => shot !== framed), { timeout: 20_000 }).toBe(true)

    await page.screenshot({ path: join(SCREENSHOT_DIR, 'screen-c-next-sheet.png') })
  })
})
