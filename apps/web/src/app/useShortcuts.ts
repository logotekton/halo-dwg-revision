import { useEffect, useRef } from 'react'
import { isCloseTabShortcut, isCycleTabShortcut, isOpenShortcut } from './shortcuts'

export interface ShortcutHandlers {
  onOpen: () => void
  onCloseTab: () => void
  onCycleTab: () => void
}

/**
 * Wires the three shell shortcuts (brief W3-01 Constraints) to a single
 * window-level keydown listener, attached once for the component's
 * lifetime. `handlers` is read through a ref (same pattern as
 * `apps/web/src/components/StatusBar.tsx`'s `statusRef`) so callers can
 * pass fresh closures every render without re-attaching the listener.
 */
export function useShortcuts(handlers: ShortcutHandlers): void {
  const handlersRef = useRef(handlers)
  useEffect(() => {
    handlersRef.current = handlers
  })

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (isOpenShortcut(event)) {
        event.preventDefault()
        handlersRef.current.onOpen()
        return
      }
      if (isCloseTabShortcut(event)) {
        event.preventDefault()
        handlersRef.current.onCloseTab()
        return
      }
      if (isCycleTabShortcut(event)) {
        event.preventDefault()
        handlersRef.current.onCycleTab()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [])
}
