import { useTranslation } from 'react-i18next'
import { DockSection } from './DockSection'
import { ChevronLeftIcon, ChevronRightIcon } from './icons'

interface LeftDockProps {
  collapsed: boolean
  onToggle: () => void
}

/**
 * Left dock (brief W3-01 Goal: "좌 도크(레이어·시트 자리)"). Real layer/sheet
 * panels are W3-04's job (docs/contracts/wave-3.md reserves the `layers.*`
 * i18n prefix for it) -- this is just the docked shell with a placeholder
 * per section, 260px wide, collapsible to a thin strip.
 */
export function LeftDock({ collapsed, onToggle }: LeftDockProps) {
  const { t } = useTranslation()
  return (
    <aside
      aria-label={t('docks.layersTitle')}
      className={`flex shrink-0 flex-col border-r border-neutral-800 bg-neutral-900 ${
        collapsed ? 'w-8' : 'w-[260px]'
      }`}
    >
      <button
        type="button"
        aria-label={collapsed ? t('docks.expandLeft') : t('docks.collapseLeft')}
        onClick={onToggle}
        className="flex h-7 shrink-0 items-center justify-center text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
      >
        {collapsed ? <ChevronRightIcon className="h-3.5 w-3.5" /> : <ChevronLeftIcon className="h-3.5 w-3.5" />}
      </button>
      {!collapsed && (
        <div className="flex-1 overflow-y-auto text-xs">
          <DockSection title={t('docks.layersTitle')} placeholder={t('docks.layersPlaceholder')} />
          <DockSection title={t('docks.sheetsTitle')} placeholder={t('docks.sheetsPlaceholder')} />
        </div>
      )}
    </aside>
  )
}
