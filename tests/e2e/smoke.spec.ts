import { expect, test } from '../../packages/testing/src/fixtures'
import { hasTestHooks, waitForStatus } from '../../packages/testing/src/electron'

/**
 * W2-07 e2e skeleton: launches the built Electron app
 * (apps/desktop/out/main/index.js) and checks the pieces every later UI
 * task depends on -- window title, header, status bar. Reused pattern for
 * new specs: docs/dev/e2e.md.
 */
test.describe('Halo CAD desktop smoke', () => {
  test('renders window title, header and status bar', async ({ window }) => {
    // Playwright's page.title() reads document.title, which
    // apps/web/index.html pins to "Halo CAD" -- the same string
    // apps/desktop/src/main/window.ts pins the native BrowserWindow title
    // to (docs/briefs/W2-07.md: "첫 창 firstWindow() -> title() === 'Halo CAD'").
    await expect(window).toHaveTitle('Halo CAD')

    const header = window.locator('header')
    await expect(header).toBeVisible()
    await expect(header).toContainText('Halo CAD')

    const statusBar = window.locator('footer')
    await expect(statusBar).toBeVisible()
    await expect(statusBar).not.toBeEmpty()
  })

  test('engine sidecar reaches ready state via window.__haloTest', async ({ window }) => {
    // docs/contracts/wave-2.md "테스트 훅": window.__haloTest only exists
    // when the renderer was started with HALO_E2E=1 *and* the W2-01 hook
    // has landed. Skip (with a reason) instead of failing when it hasn't.
    const hooksPresent = await hasTestHooks(window)
    test.skip(!hooksPresent, 'window.__haloTest 훅이 없습니다 (W2-01 미병합) -- 엔진 상태 단언을 건너뜁니다.')

    await waitForStatus(window, 'ready', 30_000)
  })
})
