import { create } from 'zustand'

/**
 * `viewer` store (docs/contracts/wave-3.md "렌더러 상태·i18n":
 * "viewer(status, overlays)"), plus `pendingCommand` per brief
 * W3-01 "Defaults for ambiguity": "명령줄은 입력 히스토리만 구현. 실행은
 * viewer 스토어의 pendingCommand에 넣어 W3-02가 소비" -- the command-line
 * component (this task) only writes `pendingCommand`; W3-02's CadHost
 * command runner is the consumer that reads and clears it.
 */
export type ViewerStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface ViewerOverlay {
  id: string
  kind: string
}

interface ViewerState {
  status: ViewerStatus
  overlays: ViewerOverlay[]
  pendingCommand: string | null
  setStatus: (status: ViewerStatus) => void
  setOverlays: (overlays: ViewerOverlay[]) => void
  submitCommand: (command: string) => void
  clearPendingCommand: () => void
}

export const useViewerStore = create<ViewerState>()((set) => ({
  status: 'idle',
  overlays: [],
  pendingCommand: null,
  setStatus: (status) => {
    set({ status })
  },
  setOverlays: (overlays) => {
    set({ overlays })
  },
  submitCommand: (command) => {
    set({ pendingCommand: command })
  },
  clearPendingCommand: () => {
    set({ pendingCommand: null })
  },
}))
