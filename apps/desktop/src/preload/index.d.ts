import type { HaloApi } from './index'

declare global {
  interface Window {
    halocad: HaloApi
    /** Test-only; see apps/desktop/src/preload/index.ts and apps/web/src/test-hooks.ts. */
    __HALO_E2E_ENABLED__: boolean
  }
}

export {}
