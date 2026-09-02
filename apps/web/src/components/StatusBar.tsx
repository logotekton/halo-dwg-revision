import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { EngineStatus } from '../api/types'
import { registerHaloTestHooks } from '../test-hooks'

/**
 * `null` before the main process has ever pushed a status (renderer just
 * mounted, no `halocad:engine:status` message received yet) — rendered as
 * the `disconnected` i18n key, which has no corresponding main-process
 * state (`docs/contracts/wave-2.md`'s state machine starts at `starting`).
 */
type DisplayState = EngineStatus['state'] | 'disconnected'

function displayState(status: EngineStatus | null): DisplayState {
  return status?.state ?? 'disconnected'
}

export function StatusBar() {
  const { t } = useTranslation()
  const [status, setStatus] = useState<EngineStatus | null>(null)

  // registerHaloTestHooks() is called once on mount with a getter that
  // always reads the latest status via this ref, so window.__haloTest
  // stays live without re-registering on every status change. Refs must be
  // written in an effect, not during render (react-hooks/refs).
  const statusRef = useRef(status)
  useEffect(() => {
    statusRef.current = status
  }, [status])

  useEffect(() => window.halocad.engine.onStatus(setStatus), [])

  useEffect(() => {
    registerHaloTestHooks(() => displayState(statusRef.current))
  }, [])

  const label = t(`status.engine.${displayState(status)}`, {
    version: status?.version ?? '',
    message: status?.message ?? '',
  })

  return (
    <footer className="flex h-7 shrink-0 items-center border-t border-neutral-800 bg-neutral-900 px-4 text-xs text-neutral-400">
      <span>{label}</span>
    </footer>
  )
}
