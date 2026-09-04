import { useTranslation } from 'react-i18next'
import type { ViewMode } from '../../../state/review'

/** The three view modes, in the order the mockup shows them (보고용 계획서 §3
 * 화면 C). Switching one is only a layer-visibility change
 * (`docs/contracts/compare-dxf.md` §9) -- the drawing is never re-opened. */
const MODES: readonly ViewMode[] = ['overlay', 'before', 'after']

export function ViewModeBar({
  mode,
  onChange,
}: {
  mode: ViewMode
  onChange: (mode: ViewMode) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1" role="group" aria-label={t('compare.review.viewMode.label')}>
      {MODES.map((candidate) => (
        <button
          key={candidate}
          type="button"
          className="hc-chip"
          data-mode={candidate}
          data-active={String(candidate === mode)}
          aria-pressed={candidate === mode}
          onClick={() => {
            onChange(candidate)
          }}
        >
          {t(`compare.review.viewMode.${candidate}`)}
        </button>
      ))}
    </div>
  )
}
