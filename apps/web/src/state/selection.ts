import { create } from 'zustand'

/**
 * `selection` store (docs/contracts/wave-3.md "렌더러 상태·i18n":
 * "selection(handles)"). Entity handles selected in the viewer -- W3-02's
 * CadHost writes here, later selection/property panels (W4-01, W3-07) read
 * from it. Empty scaffold for now: no viewer exists yet to populate it.
 */
interface SelectionState {
  handles: string[]
  setHandles: (handles: string[]) => void
  clear: () => void
}

export const useSelectionStore = create<SelectionState>()((set) => ({
  handles: [],
  setHandles: (handles) => {
    set({ handles })
  },
  clear: () => {
    set({ handles: [] })
  },
}))
