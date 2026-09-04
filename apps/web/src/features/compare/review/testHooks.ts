import { registerHaloTestHook } from '../../../test-hooks'
import { useCompareStore } from '../../../state/compare'
import { REVIEW_CANVAS_ID, useReviewStore } from '../../../state/review'
import type { ClusterDecision } from '../reviewApi'

/**
 * Screen C's `window.__haloTest` hooks (`docs/contracts/r1.md` §10).
 *
 * Registered from `ReviewScreen.tsx`'s module scope rather than from a mount
 * effect the way R1-05's `CompareApp.tsx` does its own: the e2e calls
 * `compareOpenPair` while screen B is still on screen, so the hook has to
 * exist before screen C ever mounts. `registerHaloTestHook` is a no-op unless
 * the main process was started with `HALO_E2E=1`, so nothing is exposed in a
 * normal run.
 */

const DECISIONS: readonly string[] = ['pending', 'approved', 'ignored']

/** Waits for screen C's canvas container, which `openBytes` looks up by id.
 * `openPair` only changes a store field; React still has to paint the screen
 * before the viewer has anywhere to draw. */
async function waitForViewerRoot(timeoutMs = 10_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    if (document.getElementById(REVIEW_CANVAS_ID)) return
    if (Date.now() >= deadline) {
      throw new Error(`#${REVIEW_CANVAS_ID} did not mount within ${String(timeoutMs)}ms`)
    }
    await new Promise<void>((resolve) => setTimeout(resolve, 16))
  }
}

export function registerReviewTestHooks(): void {
  registerHaloTestHook('compareOpenPair', async (pairId: string) => {
    useCompareStore.getState().openPair(pairId)
    await waitForViewerRoot()
    // Screen C's own mount effect asks for the same pair; `loadPair` joins the
    // in-flight load rather than opening the drawing twice.
    await useReviewStore.getState().loadPair(pairId)
    const state = useReviewStore.getState()
    if (state.error) throw new Error(state.error)
    if (state.renderError) throw new Error(state.renderError)
  })

  registerHaloTestHook('compareGetClusters', () => useReviewStore.getState().sidecar)

  registerHaloTestHook('compareDecide', async (number: number, decision: string) => {
    if (!DECISIONS.includes(decision)) throw new Error(`compareDecide: unknown decision "${decision}"`)
    await useReviewStore.getState().decide(number, decision as ClusterDecision)
    const state = useReviewStore.getState()
    if (state.error) throw new Error(state.error)
  })
}
