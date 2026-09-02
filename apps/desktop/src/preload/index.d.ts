import type { DmcadApi } from './index'

declare global {
  interface Window {
    dmcad: DmcadApi
  }
}

export {}
