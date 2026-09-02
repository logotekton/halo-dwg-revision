import { beforeEach, describe, expect, it } from 'vitest'
import { useSelectionStore } from './selection'

describe('useSelectionStore', () => {
  beforeEach(() => {
    useSelectionStore.setState({ handles: [] })
  })

  it('starts empty', () => {
    expect(useSelectionStore.getState().handles).toEqual([])
  })

  it('setHandles replaces the selection', () => {
    useSelectionStore.getState().setHandles(['1a', '1b'])
    expect(useSelectionStore.getState().handles).toEqual(['1a', '1b'])

    useSelectionStore.getState().setHandles(['2c'])
    expect(useSelectionStore.getState().handles).toEqual(['2c'])
  })

  it('clear empties the selection', () => {
    useSelectionStore.getState().setHandles(['1a'])
    useSelectionStore.getState().clear()
    expect(useSelectionStore.getState().handles).toEqual([])
  })
})
