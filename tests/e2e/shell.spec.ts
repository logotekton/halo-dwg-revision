import { expect, test } from '../../packages/testing/src/fixtures'

/**
 * W3-01 shell e2e: drives the real "열기" button end-to-end (no
 * window.__haloTest.openFiles yet -- that lands with W3-02/W3-03,
 * docs/contracts/wave-3.md "테스트 훅"). The native OS file dialog can't be
 * driven from Playwright, so HALO_E2E_PICK_FILES (brief W3-01 Constraints)
 * substitutes a fixed path list for it whenever HALO_E2E=1 -- set here
 * before launching the app and restored afterwards so it doesn't leak into
 * any other spec file sharing this worker process
 * (packages/testing/playwright.config.ts runs with workers: 1).
 */
test.describe('Halo CAD shell', () => {
  const PICK_FILES_ENV = 'HALO_E2E_PICK_FILES'
  const PICKED_PATHS = ['/tmp/halo-e2e-fixture-a.dxf', '/tmp/halo-e2e-fixture-b.dxf']
  // No explicit `: string | undefined` annotation here on purpose: none of
  // eslint.config.js's TypeScript-aware blocks match tests/e2e/** (they
  // all scope to apps/**/packages/**), so this directory lints under
  // plain espree, not typescript-eslint's parser -- a type annotation
  // token is a hard parse error there even though `tsc` itself handles it
  // fine (packages/testing/tsconfig.json's "include" does cover
  // ../../tests/e2e). Initializing here lets TS still infer
  // `string | undefined` without the annotation syntax. See this task's
  // report "Shared-file patch" for the proposed eslint.config.js fix.
  let previousPickFilesEnv = process.env[PICK_FILES_ENV]

  test.beforeEach(() => {
    previousPickFilesEnv = process.env[PICK_FILES_ENV]
    process.env[PICK_FILES_ENV] = PICKED_PATHS.join(',')
  })

  test.afterEach(() => {
    if (previousPickFilesEnv === undefined) {
      delete process.env[PICK_FILES_ENV]
    } else {
      process.env[PICK_FILES_ENV] = previousPickFilesEnv
    }
  })

  test('opens two tabs via 열기, switches between them, then closes one', async ({ window }) => {
    await window.getByText('열기', { exact: true }).click()

    const tabA = window.getByRole('tab', { name: 'halo-e2e-fixture-a.dxf' })
    const tabB = window.getByRole('tab', { name: 'halo-e2e-fixture-b.dxf' })
    await expect(tabA).toBeVisible()
    await expect(tabB).toBeVisible()

    // Opening activates the last picked file.
    await expect(tabB).toHaveAttribute('aria-selected', 'true')

    await tabA.click()
    await expect(tabA).toHaveAttribute('aria-selected', 'true')
    await expect(tabB).toHaveAttribute('aria-selected', 'false')

    await window.getByRole('button', { name: 'halo-e2e-fixture-b.dxf 탭 닫기' }).click()
    await expect(tabB).toHaveCount(0)
    await expect(tabA).toBeVisible()
  })
})
