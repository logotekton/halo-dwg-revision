import type { HaloApi } from './index'

declare global {
  interface Window {
    halocad: HaloApi
  }
}

export {}
