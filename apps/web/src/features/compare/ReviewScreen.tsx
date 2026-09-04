import { useTranslation } from 'react-i18next'
import { useCompareStore } from '../../state/compare'

/**
 * Screen C placeholder (brief R1-05 Goal 6; R1-08 replaces this file).
 * `#viewer-root` is kept mounted here -- not in `App.tsx` any more -- as an
 * empty container for R1-00a's CadHost, per this task's brief: "`#viewer-
 * root`... 리뷰 화면 자리표시자에 담아 두는 정도면 된다".
 */
export function ReviewScreen() {
  const { t } = useTranslation()
  const goto = useCompareStore((state) => state.goto)

  return (
    <main data-testid="review-screen" className="flex flex-1 flex-col overflow-hidden p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-sm font-semibold">{t('compare.review.title')}</h1>
        <button type="button" className="hc-btn" onClick={() => { goto('sheets') }}>
          {t('compare.review.back')}
        </button>
      </div>
      <div className="hc-panel relative flex flex-1 items-center justify-center overflow-hidden">
        <div id="viewer-root" className="absolute inset-0" style={{ backgroundColor: '#000000' }} />
        <p className="pointer-events-none relative" style={{ color: 'var(--muted)' }}>
          {t('compare.review.placeholder')}
        </p>
      </div>
    </main>
  )
}
