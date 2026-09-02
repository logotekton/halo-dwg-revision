import { useTranslation } from 'react-i18next'
import { DockSection } from './DockSection'
import { ChevronLeftIcon, ChevronRightIcon } from './icons'

interface RightDockProps {
  collapsed: boolean
  onToggle: () => void
}

/**
 * Right dock (brief W3-01 Goal: "우 도크(속성·교차검증 자리)"). Real panels
 * are W4-01 (속성/properties) and W3-07 (교차검증/crosscheck)'s job -- this
 * is just the docked shell, 320px wide, collapsible to a thin strip.
 */
export function RightDock({ collapsed, onToggle }: RightDockProps) {
  const { t } = useTranslation()
  return (
    <aside
      aria-label={t('docks.propertiesTitle')}
      className={`flex shrink-0 flex-col border-l border-neutral-800 bg-neutral-900 ${
        collapsed ? 'w-8' : 'w-[320px]'
      }`}
    >
      <button
        type="button"
        aria-label={collapsed ? t('docks.expandRight') : t('docks.collapseRight')}
        onClick={onToggle}
        className="flex h-7 shrink-0 items-center justify-center text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
      >
        {collapsed ? <ChevronLeftIcon className="h-3.5 w-3.5" /> : <ChevronRightIcon className="h-3.5 w-3.5" />}
      </button>
      {!collapsed && (
        <div className="flex-1 overflow-y-auto text-xs">
          <DockSection title={t('docks.propertiesTitle')} placeholder={t('docks.propertiesPlaceholder')} />
          <DockSection title={t('crosscheck.title')} placeholder={t('crosscheck.placeholder')} />
        </div>
      )}
    </aside>
  )
}
