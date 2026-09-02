import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDownIcon } from '../../components/icons'

interface OpenFilesButtonProps {
  recent: string[]
  onOpen: () => void
  onOpenRecent: (path: string) => void
}

/**
 * Header toolbar "열기" button (brief W3-01 Goal: "파일 열기 버튼은 preload
 * files.pickDrawings()를 호출해 경로를 documents 스토어에 넣는다") plus its
 * "최근 파일" disclosure. `onOpen`/`onOpenRecent` are provided by the caller
 * (apps/web/src/app/App.tsx), which owns pushing picked paths into the
 * `documents` store -- this component only handles the dialog trigger and
 * the recent-files dropdown UI.
 */
export function OpenFilesButton({ recent, onOpen, onOpenRecent }: OpenFilesButtonProps) {
  const { t } = useTranslation()
  const [showRecent, setShowRecent] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!showRecent) return
    const closeOnOutsideClick = (event: PointerEvent): void => {
      if (rootRef.current && event.target instanceof Node && !rootRef.current.contains(event.target)) {
        setShowRecent(false)
      }
    }
    window.addEventListener('pointerdown', closeOnOutsideClick)
    return () => {
      window.removeEventListener('pointerdown', closeOnOutsideClick)
    }
  }, [showRecent])

  return (
    <div ref={rootRef} className="relative flex items-center">
      <button
        type="button"
        title={t('files.openTooltip')}
        onClick={onOpen}
        className="rounded px-2 py-1 text-xs font-medium text-neutral-200 hover:bg-neutral-800"
      >
        {t('files.open')}
      </button>
      <button
        type="button"
        aria-label={t('files.recent')}
        aria-expanded={showRecent}
        aria-haspopup="menu"
        onClick={() => {
          setShowRecent((prev) => !prev)
        }}
        className="rounded px-1 py-1 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
      >
        <ChevronDownIcon className="h-3 w-3" />
      </button>
      {showRecent && (
        <div
          role="menu"
          aria-label={t('files.recent')}
          className="absolute left-0 top-full z-20 mt-1 min-w-[240px] rounded border border-neutral-700 bg-neutral-900 py-1 shadow-lg"
        >
          {recent.length === 0 ? (
            <span className="block px-3 py-1.5 text-xs text-neutral-600">{t('files.recentEmpty')}</span>
          ) : (
            recent.map((path) => (
              <button
                key={path}
                type="button"
                role="menuitem"
                onClick={() => {
                  onOpenRecent(path)
                  setShowRecent(false)
                }}
                className="block w-full truncate px-3 py-1.5 text-left text-xs text-neutral-200 hover:bg-neutral-800"
              >
                {path}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
