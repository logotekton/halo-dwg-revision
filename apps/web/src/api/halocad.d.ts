import type { EngineConnection, EngineStatus } from './types'

export interface HaloCadApi {
  files: {
    pickDrawings(): Promise<string[]>
  }
  app: {
    getVersion: () => Promise<string>
    platform: string
  }
  engine: {
    getConnection: () => Promise<EngineConnection>
    onStatus: (callback: (status: EngineStatus) => void) => () => void
  }
  /**
   * R1-05 (docs/contracts/r1.md §8): the folder-pick / clipboard / "open in
   * OS" primitives screens A and B need that `files.pickDrawings` does not
   * cover (a single folder rather than one-or-more files).
   */
  dialog: {
    /** Native single-folder picker. `null` when the user cancels. */
    pickFolder: (title?: string) => Promise<string | null>
  }
  clipboard: {
    writeText: (text: string) => Promise<void>
  }
  shell: {
    /** Opens a path (a produced markup DWG, an output folder) in the OS. */
    openPath: (path: string) => Promise<void>
  }
}

declare global {
  interface Window {
    /** Exposed by apps/desktop/src/preload/index.ts via contextBridge. */
    halocad: HaloCadApi
  }
}

export {}
