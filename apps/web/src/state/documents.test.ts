import { beforeEach, describe, expect, it } from 'vitest'
import { useDocumentsStore } from './documents'

function reset(): void {
  useDocumentsStore.setState({ tabs: [], activeFileId: null })
}

describe('useDocumentsStore', () => {
  beforeEach(reset)

  it('starts with no tabs and no active file', () => {
    const state = useDocumentsStore.getState()
    expect(state.tabs).toEqual([])
    expect(state.activeFileId).toBeNull()
  })

  it('openTab appends a new tab and activates it', () => {
    const { openTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a.dwg', layers: 0 })
    openTab({ fileId: 'b', name: 'b.dxf', layers: 3 })

    const state = useDocumentsStore.getState()
    expect(state.tabs).toEqual([
      { fileId: 'a', name: 'a.dwg', layers: 0 },
      { fileId: 'b', name: 'b.dxf', layers: 3 },
    ])
    expect(state.activeFileId).toBe('b')
  })

  it('openTab on an already-open file activates it instead of duplicating', () => {
    const { openTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a.dwg', layers: 0 })
    openTab({ fileId: 'b', name: 'b.dwg', layers: 0 })
    openTab({ fileId: 'a', name: 'a.dwg', layers: 0 })

    const state = useDocumentsStore.getState()
    expect(state.tabs).toHaveLength(2)
    expect(state.activeFileId).toBe('a')
  })

  it('closeTab removes the tab and activates its right neighbor when it was active', () => {
    const { openTab, closeTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })
    openTab({ fileId: 'c', name: 'c', layers: 0 })
    useDocumentsStore.setState({ activeFileId: 'b' })

    closeTab('b')

    const state = useDocumentsStore.getState()
    expect(state.tabs.map((t) => t.fileId)).toEqual(['a', 'c'])
    expect(state.activeFileId).toBe('c')
  })

  it('closeTab falls back to the left neighbor when closing the last tab', () => {
    const { openTab, closeTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })
    // openTab activates 'b' already; close it explicitly as the active tab.
    closeTab('b')

    const state = useDocumentsStore.getState()
    expect(state.tabs.map((t) => t.fileId)).toEqual(['a'])
    expect(state.activeFileId).toBe('a')
  })

  it('closeTab clears activeFileId once the last tab closes', () => {
    const { openTab, closeTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    closeTab('a')

    expect(useDocumentsStore.getState()).toMatchObject({ tabs: [], activeFileId: null })
  })

  it('closeTab leaves activeFileId untouched when closing an inactive tab', () => {
    const { openTab, closeTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })
    closeTab('a')

    expect(useDocumentsStore.getState().activeFileId).toBe('b')
  })

  it('closeTab is a no-op for an unknown fileId', () => {
    const { openTab, closeTab } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    closeTab('does-not-exist')

    expect(useDocumentsStore.getState().tabs).toHaveLength(1)
  })

  it('setActive only accepts a fileId that is actually open', () => {
    const { openTab, setActive } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })

    setActive('a')
    expect(useDocumentsStore.getState().activeFileId).toBe('a')

    setActive('unknown')
    expect(useDocumentsStore.getState().activeFileId).toBe('a')
  })

  it('cycleActive(1) moves forward and wraps past the last tab', () => {
    const { openTab, setActive, cycleActive } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })
    openTab({ fileId: 'c', name: 'c', layers: 0 })
    setActive('c')

    cycleActive(1)
    expect(useDocumentsStore.getState().activeFileId).toBe('a')
  })

  it('cycleActive(-1) moves backward and wraps before the first tab', () => {
    const { openTab, setActive, cycleActive } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    openTab({ fileId: 'b', name: 'b', layers: 0 })
    setActive('a')

    cycleActive(-1)
    expect(useDocumentsStore.getState().activeFileId).toBe('b')
  })

  it('cycleActive is a no-op with fewer than two tabs', () => {
    const { openTab, cycleActive } = useDocumentsStore.getState()
    openTab({ fileId: 'a', name: 'a', layers: 0 })
    cycleActive(1)
    expect(useDocumentsStore.getState().activeFileId).toBe('a')

    cycleActive(1)
    expect(useDocumentsStore.getState().tabs).toHaveLength(1)
  })
})
