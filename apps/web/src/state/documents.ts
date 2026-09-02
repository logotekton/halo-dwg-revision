import { create } from 'zustand'

/**
 * `documents` store (docs/contracts/wave-3.md "렌더러 상태·i18n":
 * "documents(탭, activeFileId)"). A tab's shape matches the e2e test hook
 * contract exactly (`window.__haloTest.getDocuments()`,
 * docs/contracts/wave-3.md "테스트 훅") so `apps/web/src/test-hooks.ts` can
 * expose `tabs` verbatim.
 *
 * `fileId` is the drawing-file id once W3-03's import API exists; until
 * then (brief W3-01 "Defaults for ambiguity" is silent on this, so this is
 * this task's own default) the "열기" flow uses the picked absolute path as
 * a stand-in id, since no real file id exists yet.
 */
export interface DocumentTab {
  fileId: string
  name: string
  layers: number
}

interface DocumentsState {
  tabs: DocumentTab[]
  activeFileId: string | null
  openTab: (tab: DocumentTab) => void
  closeTab: (fileId: string) => void
  setActive: (fileId: string) => void
  cycleActive: (direction: 1 | -1) => void
}

export const useDocumentsStore = create<DocumentsState>()((set, get) => ({
  tabs: [],
  activeFileId: null,

  // Re-opening an already-open file just activates its existing tab
  // instead of duplicating it (MDI convention).
  openTab: (tab) => {
    set((state) => {
      const exists = state.tabs.some((t) => t.fileId === tab.fileId)
      return {
        tabs: exists ? state.tabs : [...state.tabs, tab],
        activeFileId: tab.fileId,
      }
    })
  },

  // Closing the active tab activates its right neighbor, falling back to
  // the left neighbor at the end of the list, and to no active tab at all
  // once the last one closes.
  closeTab: (fileId) => {
    set((state) => {
      const index = state.tabs.findIndex((t) => t.fileId === fileId)
      if (index === -1) return state

      const tabs = state.tabs.filter((t) => t.fileId !== fileId)
      if (state.activeFileId !== fileId) return { tabs, activeFileId: state.activeFileId }

      const neighbor = tabs[index] ?? tabs[index - 1]
      return { tabs, activeFileId: neighbor?.fileId ?? null }
    })
  },

  setActive: (fileId) => {
    set((state) => (state.tabs.some((t) => t.fileId === fileId) ? { activeFileId: fileId } : state))
  },

  // Ctrl+Tab (direction 1) / Ctrl+Shift+Tab (direction -1) style cycling,
  // wrapping around both ends. No-op with zero or one tab.
  cycleActive: (direction) => {
    const { tabs, activeFileId } = get()
    if (tabs.length < 2) return
    const currentIndex = tabs.findIndex((t) => t.fileId === activeFileId)
    const base = currentIndex === -1 ? 0 : currentIndex
    const nextIndex = (base + direction + tabs.length) % tabs.length
    const next = tabs[nextIndex]
    if (next) set({ activeFileId: next.fileId })
  },
}))
