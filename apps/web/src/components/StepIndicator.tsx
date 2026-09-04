import { useTranslation } from 'react-i18next'
import type { CompareScreen } from '../state/compare'

/**
 * Screens A→D step indicator (brief R1-05 Goal 1: "제목 + 단계 표시
 * `A 세트 지정 · B 도곽 목록 · C 검토 · D 출력`, 현재 단계 강조"). Display
 * only -- there is no router, so clicking a step does not navigate (brief
 * "Defaults for ambiguity": "화면 전환에 라우터 라이브러리 금지").
 */
const STEPS: CompareScreen[] = ['set', 'sheets', 'review', 'export']

const STEP_LABEL_KEYS: Record<CompareScreen, string> = {
  set: 'steps.set',
  sheets: 'steps.sheets',
  review: 'steps.review',
  export: 'steps.export',
}

interface StepIndicatorProps {
  current: CompareScreen
}

export function StepIndicator({ current }: StepIndicatorProps) {
  const { t } = useTranslation()
  const currentIndex = STEPS.indexOf(current)

  return (
    <ol aria-label={t('steps.areaLabel')} className="flex items-center gap-3 text-xs">
      {STEPS.map((step, index) => {
        const isCurrent = step === current
        const isDone = index < currentIndex
        return (
          <li
            key={step}
            aria-current={isCurrent ? 'step' : undefined}
            className="flex items-center gap-1"
            style={{ color: isCurrent ? 'var(--accent)' : isDone ? 'var(--text)' : 'var(--muted)' }}
          >
            <span>{t(STEP_LABEL_KEYS[step])}</span>
            {/* ">" (not the Unicode arrow "→") so this literal falls under
                the lint rule's punctuation-only exclude pattern
                ([0-9!-/:-@[-`{-~]+) instead of needing an i18n key for a
                purely decorative separator. */}
            {index < STEPS.length - 1 && (
              <span aria-hidden="true" style={{ color: 'var(--muted)' }}>
                &gt;
              </span>
            )}
          </li>
        )
      })}
    </ol>
  )
}
