import { existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { _electron as electron, type ElectronApplication, type Page } from '@playwright/test'

// packages/testing/src/electron.ts -> repo root is three levels up.
const HERE = dirname(fileURLToPath(import.meta.url))
export const REPO_ROOT = resolve(HERE, '../../..')

const MAIN_ENTRY = join(REPO_ROOT, 'apps/desktop/out/main/index.js')
const WEB_DIST_DIR = join(REPO_ROOT, 'apps/web/dist')

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
  const require = createRequire(import.meta.url)
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
    args: [MAIN_ENTRY],
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
 */
export async function hasTestHooks(page: Page): Promise<boolean> {
  return page.evaluate(() => typeof window.__haloTest !== 'undefined')
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
