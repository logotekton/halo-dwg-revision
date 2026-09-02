import type { EngineConnection, EngineStatus } from './types'

export interface HaloCadApi {
  app: {
    getVersion: () => Promise<string>
    platform: string
  }
  engine: {
    getConnection: () => Promise<EngineConnection>
    onStatus: (callback: (status: EngineStatus) => void) => () => void
  }
}

declare global {
  interface Window {
    /** Exposed by apps/desktop/src/preload/index.ts via contextBridge. */
    halocad: HaloCadApi
  }
}

export {}
