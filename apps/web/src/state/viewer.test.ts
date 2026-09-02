import { beforeEach, describe, expect, it } from 'vitest'
import { useViewerStore } from './viewer'

describe('useViewerStore', () => {
  beforeEach(() => {
    useViewerStore.setState({ status: 'idle', overlays: [], pendingCommand: null })
  })

  it('starts idle with no overlays and no pending command', () => {
    expect(useViewerStore.getState()).toMatchObject({ status: 'idle', overlays: [], pendingCommand: null })
  })

  it('setStatus updates the status', () => {
    useViewerStore.getState().setStatus('ready')
    expect(useViewerStore.getState().status).toBe('ready')
  })

  it('setOverlays replaces the overlay list', () => {
    useViewerStore.getState().setOverlays([{ id: 'o1', kind: 'crosscheck' }])
    expect(useViewerStore.getState().overlays).toEqual([{ id: 'o1', kind: 'crosscheck' }])
  })

  it('submitCommand sets pendingCommand for the viewer command runner to consume', () => {
    useViewerStore.getState().submitCommand('ZOOM E')
    expect(useViewerStore.getState().pendingCommand).toBe('ZOOM E')
  })

  it('clearPendingCommand resets pendingCommand to null', () => {
    useViewerStore.getState().submitCommand('LINE')
    useViewerStore.getState().clearPendingCommand()
    expect(useViewerStore.getState().pendingCommand).toBeNull()
  })
})
