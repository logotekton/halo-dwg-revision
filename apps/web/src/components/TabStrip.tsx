import { useTranslation } from 'react-i18next'
import type { DocumentTab } from '../state/documents'
import { CloseIcon } from './icons'

interface TabStripProps {
  tabs: DocumentTab[]
  activeFileId: string | null
  onSelect: (fileId: string) => void
  onClose: (fileId: string) => void
}

/** MDI-style tab strip: one tab per open document (brief W3-01 Goal: "탭을 열고 전환하고 닫을 수 있는 셸"). */
export function TabStrip({ tabs, activeFileId, onSelect, onClose }: TabStripProps) {
  const { t } = useTranslation()

  if (tabs.length === 0) {
    return (
      <div className="flex h-9 shrink-0 items-center border-b border-neutral-800 bg-neutral-900 px-3 text-xs text-neutral-600">
        {t('tabs.empty')}
      </div>
    )
  }

  return (
    <div
      role="tablist"
      aria-label={t('tabs.areaLabel')}
      className="flex h-9 shrink-0 items-stretch overflow-x-auto border-b border-neutral-800 bg-neutral-900"
    >
      {tabs.map((tab) => {
        const active = tab.fileId === activeFileId
        return (
          <div
            key={tab.fileId}
            className={`flex shrink-0 items-center gap-1 border-r border-neutral-800 pl-3 pr-1 text-xs ${
              active ? 'bg-neutral-800 text-neutral-100' : 'text-neutral-400 hover:bg-neutral-800/60'
            }`}
          >
            {/* role="tab" lives on this button specifically (not the
                wrapping div) so its accessible name is just the file name
                -- putting it on the wrapper would fold the close button's
                own aria-label into the tab's computed name (ARIA
                name-from-content). */}
            <button
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => {
                onSelect(tab.fileId)
              }}
              className="max-w-[160px] truncate py-2"
            >
              {tab.name}
            </button>
            <button
              type="button"
              aria-label={t('tabs.closeTab', { name: tab.name })}
              onClick={(event) => {
                event.stopPropagation()
                onClose(tab.fileId)
              }}
              className="rounded p-1 text-neutral-500 hover:bg-neutral-700 hover:text-neutral-100"
            >
              <CloseIcon className="h-2.5 w-2.5" />
            </button>
          </div>
        )
      })}
    </div>
  )
}
