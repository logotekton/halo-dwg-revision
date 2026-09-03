import { existsSync } from 'node:fs'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '../../packages/testing/src/fixtures'
import { REPO_ROOT } from '../../packages/testing/src/electron'
import {
  createViewerSession,
  measureHeapGrowth,
  openFixture,
  pickFiles,
  viewerDocuments,
  viewerLayers,
  viewerPick,
  viewerPopulatedLayers,
  viewerSelectAndHighlight,
  viewerStatus,
} from '../../packages/testing/src/viewer'

/**
 * W3-02 viewer e2e: the real Electron app, the real `halocad://` scheme, the
 * real mlightcad viewer and the real hidden DWG converter window.
 *
 * Fixtures reach the app through `HALO_E2E_PICK_FILES`
 * (`docs/contracts/wave-3.md` "테스트 훅"); the standalone viewer page
 * (`halocad://app/viewer.html`) reads them back over the test-only IPC bridge
 * that exists only when `HALO_E2E=1`.
 *
 * The app is launched once for the whole file (rather than through the
 * `haloApp` fixture) because the tests share one viewer session on purpose:
 * that is what makes the heap measurement at the end meaningful. Every typed
 * helper lives in `packages/testing/src/viewer.ts` so this file stays plain
 * JavaScript syntax, like `smoke.spec.ts` — `tests/**` is outside the
 * workspace ESLint config's TypeScript glob.
 */

const GENERATED = join(REPO_ROOT, 'fixtures/generated')
const DXF_FIXTURE = join(GENERATED, 'F06.dxf')
const DWG_FIXTURE = join(GENERATED, 'F06.dwg')
const SCREENSHOT_DIR = join(REPO_ROOT, 'test-results/viewer')

/** F06's layer table: 0, Defpoints and six drawing layers. */
const F06_TABLE_LAYERS = 8
/** The five layers that carry entities (`fixtures/truth/F06.json` buckets). */
const F06_POPULATED_LAYERS = ['A-TEXT', 'S-BEAM', 'S-COL', 'X-GRID', 'X-TITLE']
/** `fixtures/truth/F06.json` totals.entity_count. */
const F06_ENTITIES = 86
/** 20 open/close cycles must not grow the heap by more than 10% (brief W3-02). */
const HEAP_CYCLES = 20
const HEAP_BUDGET = 0.1

test.describe.configure({ mode: 'serial' })

const session = createViewerSession()

test.beforeAll(async () => {
  test.skip(!existsSync(DXF_FIXTURE), 'fixtures/generated/F06.dxf가 없습니다')
  await mkdir(SCREENSHOT_DIR, { recursive: true })
  await session.start([DXF_FIXTURE, DWG_FIXTURE])
})

test.afterAll(async () => {
  await session.stop()
})

test('opens the DXF fixture, renders it and reports its layers', async () => {
  expect(await pickFiles(session.page)).toContain(DXF_FIXTURE)

  const opened = await openFixture(session.page, DXF_FIXTURE)
  expect(opened.entityCount).toBe(F06_ENTITIES)

  // `open()` waits for `waitUntilIdle`; the store's status is the observable
  // result of it, since the viewer has no render-finished event to relay
  // (docs/spikes/mlightcad-api.md C.4).
  await expect.poll(() => viewerStatus(session.page), { timeout: 60_000 }).toBe('ready')

  const documents = await viewerDocuments(session.page)
  expect(documents).toHaveLength(1)
  expect(documents[0]?.layers).toBe(F06_TABLE_LAYERS)
  expect(documents[0]?.entities).toBe(F06_ENTITIES)

  // Five layers carry entities: the bucket count of the stats contract, and
  // what the layer panel (W3-04) will show as non-empty.
  expect(await viewerPopulatedLayers(session.page)).toEqual(F06_POPULATED_LAYERS)
  expect(await viewerLayers(session.page)).toEqual(expect.arrayContaining(F06_POPULATED_LAYERS))

  await session.page.locator('#viewer-root canvas').first().waitFor({ state: 'visible' })
  await session.page.screenshot({ path: join(SCREENSHOT_DIR, 'f06-dxf.png') })
})

test('picks an entity by world coordinate and highlights it', async () => {
  // (8000, 23400) is the first GRID-BUBBLE insert of F06.
  const handles = await viewerPick(session.page, 8000, 23400, 400)
  expect(handles.length).toBeGreaterThan(0)

  expect(await viewerSelectAndHighlight(session.page, handles)).toEqual(handles)
  await session.page.screenshot({ path: join(SCREENSHOT_DIR, 'f06-picked.png') })
})

test('converts the DWG fixture in the hidden window and renders the result', async () => {
  test.skip(!existsSync(DWG_FIXTURE), 'fixtures/generated/F06.dwg가 없습니다')

  const opened = await openFixture(session.page, DWG_FIXTURE)
  // The default converter of ADR-0002 개정 §1, not the acad-ts fallback.
  expect(opened.converter).toBe('mlightcad-dxfout')
  expect(opened.entityCount).toBeGreaterThan(0)

  await expect.poll(() => viewerStatus(session.page), { timeout: 120_000 }).toBe('ready')

  const documents = await viewerDocuments(session.page)
  expect(documents.map((document) => document.name)).toContain('F06.dwg')
  await session.page.screenshot({ path: join(SCREENSHOT_DIR, 'f06-dwg-converted.png') })
})

test('opening and closing twenty documents keeps the heap within 10%', async () => {
  const growth = await measureHeapGrowth(session.page, DXF_FIXTURE, 'F06_dxf', HEAP_CYCLES)

  // The measured numbers belong in the run log.
  console.log(
    `heap before=${growth.before} after=${growth.after} ratio=${growth.ratio.toFixed(4)} ` +
      `perCycle=${growth.perCycleBytes}B gc=${growth.gcAvailable}`,
  )

  // `performance.memory` is quantised and reads 0 without
  // --enable-precise-memory-info (docs/spikes/mlightcad-api.md C.12); treat a
  // missing measurement as a skip rather than a pass.
  test.skip(growth.before === 0, 'performance.memory를 읽을 수 없습니다')
  expect(growth.gcAvailable).toBe(true)
  expect(growth.ratio).toBeLessThan(HEAP_BUDGET)
})
