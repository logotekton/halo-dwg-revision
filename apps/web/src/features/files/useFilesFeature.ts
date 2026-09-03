import { useCallback, useState } from 'react'
import { pickDrawings } from './api'

const STORAGE_KEY = 'halo-cad:recent-files'
const MAX_RECENT = 10

/**
 * "최근 파일" list (brief W3-01 Files-you-own: "열기 버튼·최근 파일 목록(로컬
 * 상태만)" -- local state only, no engine/project-store round trip). Backed
 * by localStorage purely as a per-machine UX convenience (survives an app
 * restart); it is not a source of truth for anything the engine or a QTO
 * run depends on (CLAUDE.md rule 5 stays satisfied: the engine remains the
 * single source of truth for models/quantities, this is just "what did I
 * open recently").
 */
function readStoredRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((entry): entry is string => typeof entry === 'string') : []
  } catch {
    return []
  }
}

function writeStoredRecent(paths: string[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(paths))
  } catch {
    // Best-effort: private browsing / storage quota / disabled storage all
    // just mean "no persistence this session", not a hard failure.
  }
}

export interface FilesFeature {
  /** Most-recently-opened paths, newest first, capped at MAX_RECENT. */
  recent: string[]
  /** Opens the native file dialog (or its e2e stand-in) and remembers the result. */
  openFiles: () => Promise<string[]>
  /** Re-opens a path already in `recent`, moving it back to the front. */
  openRecent: (path: string) => string[]
}

export function useFilesFeature(): FilesFeature {
  const [recent, setRecent] = useState<string[]>(readStoredRecent)

  const remember = useCallback((paths: string[]) => {
    setRecent((prev) => {
      const next = [...paths, ...prev.filter((path) => !paths.includes(path))].slice(0, MAX_RECENT)
      writeStoredRecent(next)
      return next
    })
  }, [])

  const openFiles = useCallback(async (): Promise<string[]> => {
    const paths = await pickDrawings()
    if (paths.length > 0) remember(paths)
    return paths
  }, [remember])

  const openRecent = useCallback(
    (path: string): string[] => {
      remember([path])
      return [path]
    },
    [remember],
  )

  return { recent, openFiles, openRecent }
}
