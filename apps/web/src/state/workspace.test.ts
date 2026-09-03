import { beforeEach, describe, expect, it } from 'vitest'
import { useWorkspaceStore } from './workspace'

describe('useWorkspaceStore', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({ project: null, drawingSet: null })
  })

  it('starts with no project and no drawing set', () => {
    expect(useWorkspaceStore.getState()).toMatchObject({ project: null, drawingSet: null })
  })

  it('setProject stores the active project', () => {
    const project = { id: 'p1', name: '샘플 프로젝트', bundlePath: '/tmp/p1.halo' }
    useWorkspaceStore.getState().setProject(project)
    expect(useWorkspaceStore.getState().project).toEqual(project)
  })

  it('setDrawingSet stores the active drawing set', () => {
    useWorkspaceStore.getState().setDrawingSet({ id: 'ds1', jobId: 'job1' })
    expect(useWorkspaceStore.getState().drawingSet).toEqual({ id: 'ds1', jobId: 'job1' })
  })

  it('setProject(null) clears the project', () => {
    useWorkspaceStore.getState().setProject({ id: 'p1', name: 'x', bundlePath: '/x' })
    useWorkspaceStore.getState().setProject(null)
    expect(useWorkspaceStore.getState().project).toBeNull()
  })
})
