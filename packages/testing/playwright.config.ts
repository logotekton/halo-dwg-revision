import { resolve } from 'node:path'
import { defineConfig } from '@playwright/test'

// packages/testing/playwright.config.ts -> repo root is two levels up.
// __dirname (not import.meta.url): this package builds as CommonJS, same
// as src/electron.ts.
const REPO_ROOT = resolve(__dirname, '../..')

/**
 * Playwright config for the Electron e2e harness (docs/briefs/W2-07.md).
 * Tests live at the repo root (tests/e2e/**) rather than under
 * packages/testing so future UI tasks can add specs without touching this
 * package. `pnpm --filter @halo-cad/testing e2e` (== `playwright test`
 * from this directory) and `tools/verify.sh --e2e` both resolve testDir via
 * this file, so cwd doesn't matter.
 */
export default defineConfig({
  testDir: resolve(REPO_ROOT, 'tests/e2e'),
  outputDir: resolve(REPO_ROOT, 'test-results'),
  // Brief: "타임아웃: 테스트 60초, 앱 기동 대기 30초" -- the 30s budget is
  // enforced inside src/electron.ts's launchHalo()/firstWindow() calls.
  timeout: 60_000,
  // Each test spawns its own Electron app (+ engine sidecar via uv); running
  // them serially avoids port/profile contention between instances.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { outputFolder: resolve(REPO_ROOT, 'playwright-report'), open: 'never' }]],
  use: {
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'off',
  },
})
