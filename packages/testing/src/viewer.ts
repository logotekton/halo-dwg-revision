import { delimiter } from 'node:path'
import type { Page } from '@playwright/test'
import { launchHalo, type HaloElectronApp } from './electron'

/**
 * Typed access to the standalone viewer page's test hook (W3-02).
 *
 * The hook itself lives in `apps/web/src/features/viewer/standalone.tsx` and is
 * installed only when the app was started with `HALO_E2E=1`
 * (`docs/contracts/wave-3.md` "테스트 훅"). It is called `__haloViewer` rather
 * than `__haloTest` because the shell's own hook (W3-01,
 * `apps/web/src/test-hooks.ts`) owns that name and has a different shape.
 *
 * Why these wrappers exist at all: `tests/e2e/**` is outside the workspace
 * ESLint config's TypeScript glob (`apps/**`, `packages/**`), so a spec file
 * that uses TypeScript-only syntax fails to parse. Keeping every type, cast and
 * `declare global` in this file lets `tests/e2e/viewer.spec.ts` stay plain
 * JavaScript syntax, the same shape `smoke.spec.ts` already has.
 */

export interface ViewerDocumentInfo {
  fileId: string
  name: string
  layers: number
  entities: number
}

export interface OpenedDrawing {
  fileId: string
  converter: string
  entityCount: number
  /** XREF definitions the converter read back out of the DWG with acad-bridge. */
  xrefs: number
  /** Text styles from the same second pass; 0 for a DXF, which needs none. */
  styles: number
  warnings: string[]
}

export interface HeapGrowth {
  before: number
  after: number
  ratio: number
  perCycleBytes: number
  gcAvailable: boolean
}

export interface ViewerLayerState {
  name: string
  visible: boolean
  frozen: boolean
}

interface ViewerHooks {
  getStatus(): string
  getDocuments(): ViewerDocumentInfo[]
  getSelection(): string[]
  pickFiles(): Promise<string[]>
  openFile(path: string): Promise<OpenedDrawing>
  pick(x: number, y: number, radius?: number): string[]
  setSelection(handles: string[]): void
  highlight(handles: string[]): void
  zoomToFit(): void
  layers(): string[]
  layerStates(): ViewerLayerState[]
  setLayerVisible(name: string, visible: boolean): boolean
  setLayersVisible(entries: Record<string, boolean>): void
  whenRenderIdle(): Promise<void>
  populatedLayers(): string[]
  close(fileId: string): Promise<void>
  dispose(): Promise<void>
  heapUsedBytes(): number | null
  viewerDocumentCount(): number
  renderLoad(): { topLevel: number; inBlocks: number; total: number }
  collectGarbage(): Promise<boolean>
}

declare global {
  interface Window {
    __haloViewer?: ViewerHooks
  }
}

/**
 * The page-side hook lookup, written as source rather than a shared function:
 * `page.evaluate` serialises its callback, so a helper from this module's scope
 * would not exist in the browser. Every wrapper below repeats these two lines
 * for that reason, and throws a message that names the cause instead of failing
 * with "undefined is not a function".
 */
const NO_HOOK = 'the viewer page exposes no __haloViewer hook (HALO_E2E=1?)'

/** The standalone viewer harness page served by the app scheme. */
export const VIEWER_PAGE_URL = 'halocad://app/viewer.html'

/**
 * One Electron app driving the viewer page for a whole spec file.
 *
 * Returned as a closure rather than left to the spec's own `let` bindings so
 * `tests/e2e/**` needs no type annotation of its own — see the note at the top
 * of this file.
 */
export function createViewerSession(): {
  start(fixturePaths: string[]): Promise<void>
  stop(): Promise<void>
  readonly page: Page
  /** PID of the Electron main process, for out-of-band RSS sampling. */
  pid(): number
} {
  let app: HaloElectronApp | null = null
  return {
    async start(fixturePaths: string[]): Promise<void> {
      // Read by the main process's test-only IPC bridge
      // (apps/desktop/src/main/convert/e2e.ts), which is the stand-in for
      // W3-01's native file dialog.
      process.env.HALO_E2E_PICK_FILES = fixturePaths.join(delimiter)
      app = await launchHalo()
      if (process.env.HALO_E2E_TRACE === '1') {
        const child = app.app.process()
        child.stderr?.on('data', (chunk: Buffer) => {
          process.stderr.write(`[electron] ${chunk.toString()}`)
        })
        child.stdout?.on('data', (chunk: Buffer) => {
          process.stderr.write(`[electron] ${chunk.toString()}`)
        })
      }
      await gotoViewerPage(app.window)
    },
    async stop(): Promise<void> {
      await app?.close()
      app = null
    },
    get page(): Page {
      if (!app) throw new Error('viewer session has not been started')
      return app.window
    },
    pid(): number {
      if (!app) throw new Error('viewer session has not been started')
      return app.app.process().pid ?? 0
    },
  }
}

/**
 * Navigates the app's first window to the viewer page and waits for its hook.
 *
 * The initial `load` wait is not optional: `firstWindow()` resolves as soon as
 * the CDP target exists, which can be *before* main's own
 * `loadURL(index.html)` has committed, and navigating on top of an in-flight
 * load is rejected with "interrupted by another navigation".
 */
export async function gotoViewerPage(page: Page, timeoutMs = 30_000): Promise<void> {
  await page.waitForLoadState('load')
  await page.goto(VIEWER_PAGE_URL, { waitUntil: 'load' })
  await page.waitForFunction(() => window.__haloViewer !== undefined, undefined, {
    timeout: timeoutMs,
  })
}

export function pickFiles(page: Page): Promise<string[]> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.pickFiles()
  }, NO_HOOK)
}

/** Opens one fixture path; a `.dwg` goes through the hidden converter window. */
export function openFixture(page: Page, path: string): Promise<OpenedDrawing> {
  return page.evaluate(
    (args) => {
      const hooks = window.__haloViewer
      if (!hooks) throw new Error(args.message)
      return hooks.openFile(args.path)
    },
    { path, message: NO_HOOK },
  )
}

export function viewerStatus(page: Page): Promise<string> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.getStatus()
  }, NO_HOOK)
}

export function viewerDocuments(page: Page): Promise<ViewerDocumentInfo[]> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.getDocuments()
  }, NO_HOOK)
}

export function viewerLayers(page: Page): Promise<string[]> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.layers()
  }, NO_HOOK)
}

/** The layer table with the on/off and frozen flags (R1-00a). */
export function viewerLayerStates(page: Page): Promise<ViewerLayerState[]> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.layerStates()
  }, NO_HOOK)
}

/**
 * Applies a view mode and waits for the repaint.
 *
 * The wait is part of the helper on purpose: turning a layer back on can need
 * entities the viewer never converted while it was hidden
 * (`AcTrView2d.convertMissingEntitiesOnLayer`), so a screenshot taken straight
 * after the toggle can catch a half-drawn frame.
 */
export function viewerSetLayersVisible(
  page: Page,
  entries: Record<string, boolean>,
): Promise<void> {
  return page.evaluate(
    async (args) => {
      const hooks = window.__haloViewer
      if (!hooks) throw new Error(args.message)
      hooks.setLayersVisible(args.entries)
      await hooks.whenRenderIdle()
    },
    { entries, message: NO_HOOK },
  )
}

/** Layers that actually carry a top-level entity, sorted. */
export function viewerPopulatedLayers(page: Page): Promise<string[]> {
  return page.evaluate((message) => {
    const hooks = window.__haloViewer
    if (!hooks) throw new Error(message)
    return hooks.populatedLayers()
  }, NO_HOOK)
}

/** Hit test in drawing coordinates; the radius is in pixels (spike C.3). */
export function viewerPick(page: Page, x: number, y: number, radiusPx = 8): Promise<string[]> {
  return page.evaluate(
    (args) => {
      const hooks = window.__haloViewer
      if (!hooks) throw new Error(args.message)
      return hooks.pick(args.x, args.y, args.radius)
    },
    { x, y, radius: radiusPx, message: NO_HOOK },
  )
}

export async function viewerSelectAndHighlight(page: Page, handles: string[]): Promise<string[]> {
  return page.evaluate(
    (args) => {
      const hooks = window.__haloViewer
      if (!hooks) throw new Error(args.message)
      hooks.setSelection(args.handles)
      hooks.highlight(args.handles)
      return hooks.getSelection()
    },
    { handles, message: NO_HOOK },
  )
}

/**
 * Opens and closes the same fixture `cycles` times twice over: once to warm the
 * heap up, once as the measurement. Returns the relative growth of the second
 * run, which is what the leak budget applies to.
 *
 * The warm-up matters: the first opens pay for the lazily imported viewer
 * chunk, the worker pools, the glyph atlas and V8's compiled code for
 * once-only paths. Measured decay on F06 is ~158 kB/cycle over the first ten
 * cycles and ~86 kB/cycle from the twentieth on
 * (`docs/dev/viewer-integration.md`).
 */
export function measureHeapGrowth(
  page: Page,
  fixturePath: string,
  fileId: string,
  cycles: number,
): Promise<HeapGrowth> {
  return page.evaluate(
    async (args) => {
      const hooks = window.__haloViewer
      if (!hooks) throw new Error(args.message)
      let gcAvailable = false
      const cycle = async (): Promise<void> => {
        await hooks.openFile(args.fixturePath)
        await hooks.close(args.fileId)
      }
      const settle = async (): Promise<number> => {
        gcAvailable = await hooks.collectGarbage()
        const first = hooks.heapUsedBytes() ?? 0
        gcAvailable = (await hooks.collectGarbage()) || gcAvailable
        // Two readings, lower wins: the collector can leave a little behind on
        // the first pass and the difference is noise at this scale.
        return Math.min(first, hooks.heapUsedBytes() ?? first)
      }

      for (let round = 0; round < args.cycles; round += 1) await cycle()
      const before = await settle()
      for (let round = 0; round < args.cycles; round += 1) await cycle()
      const after = await settle()
      return {
        before,
        after,
        gcAvailable,
        ratio: before === 0 ? 0 : (after - before) / before,
        perCycleBytes: Math.round((after - before) / args.cycles),
      }
    },
    { fixturePath, fileId, cycles, message: NO_HOOK },
  )
}
