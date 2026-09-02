/**
 * `window.__haloTest` (`docs/contracts/wave-2.md` "테스트 훅"): exposed only
 * when the Electron main process was started with `HALO_E2E=1`, relayed
 * into the renderer's main world as `window.__HALO_E2E_ENABLED__` by
 * `apps/desktop/src/preload/index.ts` (not part of the `window.halocad`
 * contract itself — a separate, test-only global). Consumed by W2-07's
 * Playwright e2e harness.
 */
export interface HaloTestHooks {
  getStatus(): string
}

declare global {
  interface Window {
    __HALO_E2E_ENABLED__?: boolean
    __haloTest?: HaloTestHooks
  }
}

/**
 * Registers `window.__haloTest`, gated on `window.__HALO_E2E_ENABLED__`.
 * `getStatus` should return the current engine state machine value (e.g.
 * `'ready'`), not the localized status-bar label — locale-independent and
 * stable for automated assertions.
 */
export function registerHaloTestHooks(getStatus: () => string): void {
  if (typeof window === 'undefined' || window.__HALO_E2E_ENABLED__ !== true) return
  window.__haloTest = { getStatus }
}

export {}
