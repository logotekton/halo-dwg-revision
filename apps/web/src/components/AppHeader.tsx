import { useTranslation } from 'react-i18next'
import { OpenFilesButton } from '../features/files/OpenFilesButton'
import { MenuBar, type MenuDef } from './MenuBar'

interface AppHeaderProps {
  title: string
  canCloseActiveTab: boolean
  recentFiles: string[]
  leftDockCollapsed: boolean
  rightDockCollapsed: boolean
  onOpen: () => void
  onOpenRecent: (path: string) => void
  onCloseActiveTab: () => void
  onToggleLeftDock: () => void
  onToggleRightDock: () => void
}

export function AppHeader(props: AppHeaderProps) {
  const { t } = useTranslation()
  const {
    title,
    canCloseActiveTab,
    recentFiles,
    leftDockCollapsed,
    rightDockCollapsed,
    onOpen,
    onOpenRecent,
    onCloseActiveTab,
    onToggleLeftDock,
    onToggleRightDock,
  } = props

  // Items without a real handler render disabled rather than being left
  // out (brief W3-01 Constraints: "동작 없는 항목은 비활성으로 표시") --
  // 편집(Edit)/도움말(Help) have no wired commands yet (Wave 4+).
  const menus: MenuDef[] = [
    {
      key: 'file',
      label: t('menu.file.label'),
      items: [
        { key: 'open', label: t('menu.file.open'), onSelect: onOpen },
        {
          key: 'close-tab',
          label: t('menu.file.closeTab'),
          onSelect: onCloseActiveTab,
          disabled: !canCloseActiveTab,
        },
      ],
    },
    {
      key: 'edit',
      label: t('menu.edit.label'),
      items: [
        { key: 'undo', label: t('menu.edit.undo'), disabled: true },
        { key: 'redo', label: t('menu.edit.redo'), disabled: true },
      ],
    },
    {
      key: 'view',
      label: t('menu.view.label'),
      items: [
        {
          key: 'toggle-left',
          label: t('menu.view.toggleLeftDock'),
          onSelect: onToggleLeftDock,
          pressed: !leftDockCollapsed,
        },
        {
          key: 'toggle-right',
          label: t('menu.view.toggleRightDock'),
          onSelect: onToggleRightDock,
          pressed: !rightDockCollapsed,
        },
      ],
    },
    {
      key: 'help',
      label: t('menu.help.label'),
      items: [{ key: 'about', label: t('menu.help.about'), disabled: true }],
    },
  ]

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-neutral-800 bg-neutral-900 px-4">
      <span className="text-sm font-semibold text-neutral-100">{title}</span>
      <OpenFilesButton recent={recentFiles} onOpen={onOpen} onOpenRecent={onOpenRecent} />
      <MenuBar menus={menus} />
    </header>
  )
}
