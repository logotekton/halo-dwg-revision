import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { _electron as electron, type ElectronApplication, type Page } from '@playwright/test'

// packages/testing/src/electron.ts -> repo root is three levels up. This
// package builds as CommonJS (no "type": "module" in package.json, matching
// apps/desktop/apps/web's non-ESM TS packages) so Playwright's built-in TS
// loader (esbuild, cjs output) can require() it -- __dirname is the plain
// CJS global, not import.meta.url.
export const REPO_ROOT = resolve(__dirname, '../../..')

const MAIN_ENTRY = join(REPO_ROOT, 'apps/desktop/out/main/index.js')
const WEB_DIST_DIR = join(REPO_ROOT, 'apps/web/dist')
// Launch target passed to _electron.launch()'s args: the apps/desktop
// *package directory* (its package.json's "main" points at
// out/main/index.js), not MAIN_ENTRY's bare file path -- see the
// "Electron app path resolution" note on launchHalo() below for why this
// matters, not just style.
const APP_DIR = join(REPO_ROOT, 'apps/desktop')

export interface LaunchHaloOptions {
  /** Time budget for the app to spawn and its first BrowserWindow to appear.
   * Brief docs/briefs/W2-07.md: "앱 기동 대기 30초". */
  launchTimeoutMs?: number
}

export interface HaloElectronApp {
  app: ElectronApplication
  window: Page
  close: () => Promise<void>
}

/**
 * Resolves the Electron executable via `require('electron')`. Per
 * docs/briefs/W2-07.md "Defaults for ambiguity": ideally this would resolve
 * `apps/desktop`'s own `electron` devDependency, but the workspace's
 * `node-linker=isolated` (.npmrc) keeps each package's node_modules
 * strictly to its own declared dependencies, so packages/testing pins its
 * own `electron` devDependency at the same version instead (recorded in
 * the task report's Decisions).
 */
function resolveElectronExecutable(): string {
  // The `electron` package's main export is the path to its native binary
  // (a string), not JS API bindings -- that's only true inside a running
  // Electron process.
  return require('electron') as unknown as string
}

function assertBuildOutputsExist(): void {
  const missing = [MAIN_ENTRY, WEB_DIST_DIR].filter((p) => !existsSync(p))
  if (missing.length === 0) return
  throw new Error(
    [
      'Halo CAD 빌드 산출물을 찾을 수 없습니다. 저장소 루트에서 `pnpm build`를 먼저 실행하세요.',
      '누락된 경로:',
      ...missing.map((p) => `  - ${p}`),
    ].join('\n'),
  )
}

/**
 * Launches the built Electron app (`apps/desktop/out/main/index.js`) with
 * `HALO_E2E=1` (docs/contracts/wave-2.md "테스트 훅") via Playwright's
 * `_electron.launch`, and returns its first window.
 *
 * Electron app path resolution (why `args` is `[APP_DIR]`, not
 * `[MAIN_ENTRY]`): `docs/briefs/W2-07.md`'s literal recipe is
 * `_electron.launch({ args: [mainPath], ... })`. Passing MAIN_ENTRY's bare
 * file path (`apps/desktop/out/main/index.js`) verbatim reproduces a real
 * `apps/desktop` bug -- confirmed empirically, not guessed: when Electron
 * is launched with a path to a *file* instead of a *directory containing
 * package.json*, `app.getAppPath()` resolves to that file's directory
 * (`apps/desktop/out/main`) instead of the package root
 * (`apps/desktop`, what `electron .` / `pnpm --filter @halo-cad/desktop
 * start` gets). Both `apps/desktop/src/main/protocol.ts`'s
 * `resolveWebDistDir()` and `index.ts`'s `engineDevDir()` derive their
 * paths from `app.getAppPath() + '..'` segments, so the wrong base makes
 * both resolve to nonexistent directories: `halocad://app/*` 404s (empty
 * `document.title`, blank window) and the engine's `uv run` spawn gets a
 * nonexistent `cwd`, which -- also confirmed empirically -- doesn't just
 * fail the spawn but wedges the whole process (including Chromium's
 * `--remote-debugging-port` CDP endpoint that `_electron.launch` itself
 * depends on, so the launch call times out with no diagnostic pointing at
 * the real cause). Launching with the package *directory* instead resolves
 * `app.getAppPath()` the same way `electron .` does (via `package.json`'s
 * `main` field), sidestepping the bug without touching `apps/desktop/**`
 * (outside this task's "Files you own"). See the report's "Shared-file
 * patch" for the proposed fix to `resolveWebDistDir()`/`engineDevDir()`
 * themselves. `MAIN_ENTRY` is still used by `assertBuildOutputsExist()` to
 * check the actual build output exists.
 */
export async function launchHalo(opts: LaunchHaloOptions = {}): Promise<HaloElectronApp> {
  assertBuildOutputsExist()

  const timeout = opts.launchTimeoutMs ?? 30_000

  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined) env[key] = value
  }
  // Force the production halocad://app protocol path
  // (apps/desktop/src/main/window.ts) instead of an ambient dev-server URL
  // left over from a `pnpm dev` run in the same shell.
  delete env.HALO_WEB_DEV_SERVER_URL
  env.HALO_E2E = '1'

  const app = await electron.launch({
    executablePath: resolveElectronExecutable(),
    args: [APP_DIR],
    env,
    timeout,
  })

  const window = await app.firstWindow({ timeout })

  return {
    app,
    window,
    close: async () => {
      await app.close()
    },
  }
}

/**
 * True when the renderer was started with HALO_E2E=1 and exposes
 * `window.__haloTest` (W2-01). Parameter is named `page`, not `window`,
 * so the arrow function passed to `evaluate()` resolves the bare
 * `window` identifier to the browser's global (lib.dom) `Window`
 * instead of shadowing it with this Playwright `Page` value.
 *
 * Polls for up to `timeoutMs` rather than checking once: `firstWindow()`
 * resolves as soon as the page's CDP target exists, which can be before
 * React has mounted `StatusBar` (the component that calls
 * `registerHaloTestHooks()`, `apps/web/src/components/StatusBar.tsx`) --
 * checking exactly once raced that mount and skipped the ready-state test
 * even with W2-01 merged. A genuinely absent hook (W2-01 not merged) still
 * correctly resolves `false` once the timeout elapses.
 */
export async function hasTestHooks(page: Page, timeoutMs = 5_000): Promise<boolean> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    if (await page.evaluate(() => typeof window.__haloTest !== 'undefined')) return true
    if (Date.now() >= deadline) return false
    await page.waitForTimeout(100)
  }
}

/**
 * Polls `window.__haloTest.getStatus()` until it equals `state` or
 * `timeoutMs` elapses. Callers should check `hasTestHooks()` first (or
 * `test.skip`) -- this rejects with the last observed status if the hook
 * itself never appears.
 */
export async function waitForStatus(page: Page, state: string, timeoutMs = 30_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let last: string | undefined
  for (;;) {
    last = await page.evaluate(() => window.__haloTest?.getStatus())
    if (last === state) return
    if (Date.now() >= deadline) break
    await page.waitForTimeout(250)
  }
  throw new Error(
    `window.__haloTest.getStatus()가 ${String(timeoutMs)}ms 안에 '${state}' 상태에 도달하지 못했습니다 ` +
      `(마지막 값: ${String(last)}).`,
  )
}

declare global {
  interface Window {
    __haloTest?: { getStatus(): string }
  }
}
