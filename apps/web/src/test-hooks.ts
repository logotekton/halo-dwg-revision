/**
 * `window.__haloTest` (`docs/contracts/wave-2.md` "테스트 훅", extended by
 * `docs/contracts/wave-3.md`): exposed only when the Electron main process
 * was started with `HALO_E2E=1`, relayed into the renderer's main world as
 * `window.__HALO_E2E_ENABLED__` by `apps/desktop/src/preload/index.ts` (not
 * part of the `window.halocad` contract itself — a separate, test-only
 * global). Consumed by W2-07's Playwright e2e harness.
 *
 * `openFiles` (docs/contracts/wave-3.md) is intentionally not part of this
 * interface yet — brief W3-01: "test-hooks.ts: getDocuments 추가(openFiles는
 * W3-02/03 후)". It lands once the real import pipeline (W3-02/W3-03) is
 * merged.
 */
export interface HaloTestHooks {
  getStatus(): string
  getDocuments(): { fileId: string; name: string; layers: number }[]
}

declare global {
  interface Window {
    __HALO_E2E_ENABLED__?: boolean
    __haloTest?: HaloTestHooks
  }
}

// Multiple independent components each register one getter (StatusBar ->
// getStatus, the app shell -> getDocuments) rather than one component
// owning the whole object, so registration must merge instead of
// overwrite -- otherwise the second registerHaloTestHook call would wipe
// out the first one's key. Module-level (not component state) so it
// survives across the individually-registering components' own
// mount/unmount cycles for the lifetime of this module.
let registeredHooks: Partial<HaloTestHooks> = {}

/**
 * Registers one getter on `window.__haloTest`, merging with any previously
 * registered getters. No-op unless the main process was started with
 * `HALO_E2E=1` (see the module doc comment above).
 */
export function registerHaloTestHook<K extends keyof HaloTestHooks>(key: K, getter: HaloTestHooks[K]): void {
  if (typeof window === 'undefined' || window.__HALO_E2E_ENABLED__ !== true) return
  registeredHooks = { ...registeredHooks, [key]: getter }
  window.__haloTest = registeredHooks as HaloTestHooks
}

export {}
