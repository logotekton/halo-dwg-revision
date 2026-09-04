import { useEffect } from 'react'
import { registerHaloTestHook } from '../../test-hooks'
import { useCompareStore, type CompareScreen } from '../../state/compare'
import { ExportScreen } from './ExportScreen'
import { ReviewScreen } from './ReviewScreen'
import { SetScreen } from './SetScreen'
import { SheetListScreen } from './SheetListScreen'

const SCREENS: readonly CompareScreen[] = ['set', 'sheets', 'review', 'export']

function isCompareScreen(value: string): value is CompareScreen {
  return (SCREENS as readonly string[]).includes(value)
}

/**
 * Renders the current screen (A-D) and registers the `compare*` test hooks
 * (docs/contracts/r1.md §10) once, for the lifetime of the app -- the same
 * "register on mount, read the store live via getState()" pattern
 * `apps/web/src/app/App.tsx` used for `getDocuments` before this task.
 */
export function CompareApp() {
  useEffect(() => {
    registerHaloTestHook('compareStartSet', async ({ beforeDir, afterDir, runDate }) => {
      const store = useCompareStore.getState()
      store.reset()
      useCompareStore.setState({ beforeDir, afterDir, runDate })
      await useCompareStore.getState().startSet()

      const state = useCompareStore.getState()
      if (state.error) throw new Error(state.error)
      if (state.toast) throw new Error(`compareStartSet stalled on toast: ${state.toast}`)
      if (!state.compareSetId) throw new Error('compareStartSet: no compare_set_id was created')
      return state.compareSetId
    })

    registerHaloTestHook('compareGetScreen', () => useCompareStore.getState().screen)

    registerHaloTestHook('compareGoto', (screen: string) => {
      if (!isCompareScreen(screen)) throw new Error(`compareGoto: unknown screen "${screen}"`)
      useCompareStore.getState().goto(screen)
    })

    registerHaloTestHook('compareGetSummary', () => useCompareStore.getState().summary)

    registerHaloTestHook('compareGetPairs', () => useCompareStore.getState().pairs)

    registerHaloTestHook('compareRunCompare', async () => {
      await useCompareStore.getState().startRun()
      const state = useCompareStore.getState()
      if (state.error) throw new Error(state.error)
    })
  }, [])

  const screen = useCompareStore((state) => state.screen)

  switch (screen) {
    case 'set':
      return <SetScreen />
    case 'sheets':
      return <SheetListScreen />
    case 'review':
      return <ReviewScreen />
    case 'export':
      return <ExportScreen />
  }
}
