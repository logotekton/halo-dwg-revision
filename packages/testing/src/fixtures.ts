import { test as base, type ConsoleMessage } from '@playwright/test'
import { launchHalo, type HaloElectronApp } from './electron'

interface HaloFixtures {
  haloApp: HaloElectronApp
  window: HaloElectronApp['window']
}

/**
 * Playwright test fixture that launches the built Halo CAD Electron app
 * once per test and tears it down afterwards. On failure the `window`
 * fixture attaches a screenshot and the accumulated console log to the
 * test report -- docs/briefs/W2-07.md: "실패 시 test-results/에 스크린샷·
 * 비디오 없이 스크린샷만, 콘솔 메시지를 첨부."
 */
export const test = base.extend<HaloFixtures>({
  haloApp: async ({}, use) => {
    const halo = await launchHalo()
    await use(halo)
    await halo.close()
  },

  window: async ({ haloApp }, use, testInfo) => {
    const { window } = haloApp
    const consoleLog: string[] = []
    const onConsole = (msg: ConsoleMessage): void => {
      consoleLog.push(`[${msg.type()}] ${msg.text()}`)
    }
    window.on('console', onConsole)

    await use(window)

    window.off('console', onConsole)

    if (testInfo.status !== 'passed' && testInfo.status !== 'skipped') {
      if (!window.isClosed()) {
        await window
          .screenshot({ path: testInfo.outputPath('failure.png') })
          .then((body) => testInfo.attach('failure-screenshot.png', { body, contentType: 'image/png' }))
          .catch(() => {
            // Best-effort: the window/app may already be gone by teardown time.
          })
      }
      if (consoleLog.length > 0) {
        await testInfo.attach('console-log.txt', {
          body: consoleLog.join('\n'),
          contentType: 'text/plain',
        })
      }
    }
  },
})

export { expect } from '@playwright/test'
