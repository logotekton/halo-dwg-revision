/**
 * Minimal `viewer` and `selection` stores.
 *
 * `docs/contracts/wave-3.md` ("렌더러 상태") gives the Zustand stores to W3-01,
 * which is landing in parallel; this file is the self-contained stand-in the
 * brief asks for. It uses the same names and shapes (`viewer.status`,
 * `viewer.overlays`, `selection.handles`) so the swap is a re-export, and it
 * pulls in no dependency: `useSyncExternalStore` is enough for a store this
 * small, and adding Zustand here would collide with W3-01's own dependency
 * change.
 */

import { useSyncExternalStore } from 'react';
import type { CadHostStatus, CadHostWarning } from '@halo-cad/cad-core';

export interface ViewerDocument {
  fileId: string;
  name: string;
  entityCount: number;
  layers: number;
  layouts: number;
  tier: 'A' | 'B' | 'C';
  durationMs: number;
}

export interface ViewerState {
  status: CadHostStatus;
  activeFileId: string | null;
  documents: ViewerDocument[];
  overlays: string[];
  warnings: CadHostWarning[];
  /** Set when an open failed; the panel shows it via `viewer.error`. */
  error: string | null;
  progress: { percentage: number; stage: string } | null;
}

export interface SelectionState {
  handles: string[];
}

type Listener = () => void;

function createStore<T>(initial: T): {
  get: () => T;
  set: (next: T | ((previous: T) => T)) => void;
  subscribe: (listener: Listener) => () => void;
} {
  let state = initial;
  const listeners = new Set<Listener>();
  return {
    get: () => state,
    set: (next) => {
      const value = typeof next === 'function' ? (next as (previous: T) => T)(state) : next;
      if (Object.is(value, state)) return;
      state = value;
      for (const listener of listeners) listener();
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

const viewerStore = createStore<ViewerState>({
  status: 'idle',
  activeFileId: null,
  documents: [],
  overlays: [],
  warnings: [],
  error: null,
  progress: null,
});

const selectionStore = createStore<SelectionState>({ handles: [] });

export const viewer = {
  getState: viewerStore.get,
  setState: viewerStore.set,
  subscribe: viewerStore.subscribe,
};

export const selection = {
  getState: selectionStore.get,
  setState: selectionStore.set,
  subscribe: selectionStore.subscribe,
};

export function useViewerState(): ViewerState {
  return useSyncExternalStore(viewerStore.subscribe, viewerStore.get, viewerStore.get);
}

export function useSelectionState(): SelectionState {
  return useSyncExternalStore(selectionStore.subscribe, selectionStore.get, selectionStore.get);
}
