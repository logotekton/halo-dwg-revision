import { create } from 'zustand'

/**
 * `workspace` store (docs/contracts/wave-3.md "렌더러 상태·i18n":
 * "workspace(project, drawingSet)"). Both fields stay `null` until W3-03's
 * project-bundle API is wired up (brief W3-01 Goal: "실제 임포트는 W3-02/03
 * 병합 후 연결") -- this task only defines the shape and setters other
 * tasks will call into.
 */
export interface WorkspaceProject {
  id: string
  name: string
  bundlePath: string
}

export interface WorkspaceDrawingSet {
  id: string
  jobId?: string
}

interface WorkspaceState {
  project: WorkspaceProject | null
  drawingSet: WorkspaceDrawingSet | null
  setProject: (project: WorkspaceProject | null) => void
  setDrawingSet: (drawingSet: WorkspaceDrawingSet | null) => void
}

export const useWorkspaceStore = create<WorkspaceState>()((set) => ({
  project: null,
  drawingSet: null,
  setProject: (project) => {
    set({ project })
  },
  setDrawingSet: (drawingSet) => {
    set({ drawingSet })
  },
}))
