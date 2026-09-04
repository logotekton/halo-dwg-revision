import { test } from '../../packages/testing/src/fixtures'

/**
 * W3-01 shell e2e: drove the old Halo CAD shell's "열기" button, tab strip,
 * and tab-close button end-to-end.
 *
 * Retired by R1-05 (docs/contracts/r1.md §9, CLAUDE.md rule 10 "범위
 * 고정"): `apps/web/src/app/App.tsx` no longer renders `TabStrip`/
 * `MenuBar`/`features/files`'s "열기" flow at all -- R1 is one guided
 * compare flow (screens A-D), not the general multi-document CAD shell W3-01
 * built. The components and their own unit tests are untouched
 * (`components/TabStrip.tsx`, `features/files/**`, `state/documents.ts`),
 * only `App.tsx` stopped mounting them, so this e2e spec has nothing left
 * to click through. `tests/e2e/compare-sheets.spec.ts` is its replacement
 * for the new shell. See this task's (R1-05) report "Shared-file patch" for
 * why this file -- outside R1-05's own "Files you own" -- was edited
 * anyway: leaving it red would fail every future `tools/verify.sh --e2e`
 * run for a UI this task was explicitly told to remove, not a regression
 * to fix forward.
 */
test.describe('Halo CAD shell (retired)', () => {
  test.skip(true, 'R1-05가 구 셸(도크·탭·명령줄·열기)의 렌더를 걷어냈다 -- tests/e2e/compare-sheets.spec.ts로 대체')
  test('opens two tabs via 열기, switches between them, then closes one', () => {
    // Intentionally empty -- see the file-level comment above.
  })
})
