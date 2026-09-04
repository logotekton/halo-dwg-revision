import { useCallback, useEffect, useState } from 'react'
import { getFileXrefs, type XrefLink } from './api'

export interface UseXrefLinksResult {
  links: XrefLink[]
  loading: boolean
  error: string | null
  refetch: () => void
}

interface FetchResult {
  requestId: number
  links: XrefLink[]
  error: string | null
}

/**
 * Fetches `GET /files/{id}/xrefs` for one host file and keeps it current.
 * `fileId === null` (no active document) just yields an empty, non-loading
 * result -- callers do not need to guard the hook call itself.
 *
 * `loading` is derived from comparing the latest completed fetch's
 * `requestId` against the current `generation` (bumped by `fileId`
 * changing or `refetch()`), rather than a separate `setLoading` call, so
 * the effect body itself never calls `setState` synchronously
 * (`react-hooks/set-state-in-effect` -- the one `setResult` call below runs
 * inside the fetch's `.then`/`.catch`, not the effect body itself).
 */
export function useXrefLinks(fileId: string | null): UseXrefLinksResult {
  const [generation, setGeneration] = useState(0)
  const [result, setResult] = useState<FetchResult | null>(null)

  const refetch = useCallback(() => {
    setGeneration((g) => g + 1)
  }, [])

  useEffect(() => {
    if (!fileId) return
    let cancelled = false
    const requestId = generation
    getFileXrefs(fileId)
      .then((links) => {
        if (!cancelled) setResult({ requestId, links, error: null })
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setResult({
            requestId,
            links: [],
            error: err instanceof Error ? err.message : String(err),
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [fileId, generation])

  if (!fileId) {
    return { links: [], loading: false, error: null, refetch }
  }
  if (result?.requestId !== generation) {
    return { links: [], loading: true, error: null, refetch }
  }
  return { links: result.links, loading: false, error: result.error, refetch }
}
