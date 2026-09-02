import { useTranslation } from 'react-i18next'

export function StatusBar() {
  const { t } = useTranslation()

  return (
    <footer className="flex h-7 shrink-0 items-center border-t border-neutral-800 bg-neutral-900 px-4 text-xs text-neutral-400">
      <span>{t('status.engineDisconnected')}</span>
    </footer>
  )
}
