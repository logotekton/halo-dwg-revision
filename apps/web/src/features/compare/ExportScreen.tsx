import { useTranslation } from 'react-i18next'
import { useCompareStore } from '../../state/compare'

/** Screen D placeholder (brief R1-05 Goal 6; R1-10 replaces this file). */
export function ExportScreen() {
  const { t } = useTranslation()
  const goto = useCompareStore((state) => state.goto)

  return (
    <main data-testid="export-screen" className="flex flex-1 flex-col items-center justify-center gap-3 p-4">
      <h1 className="text-sm font-semibold">{t('compare.export.title')}</h1>
      <p style={{ color: 'var(--muted)' }}>{t('compare.export.placeholder')}</p>
      <button type="button" className="hc-btn" onClick={() => { goto('sheets') }}>
        {t('compare.export.back')}
      </button>
    </main>
  )
}
