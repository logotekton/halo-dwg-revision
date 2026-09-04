import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCompareStore } from '../../state/compare'
import { unmatchedFrameCandidates } from './pairFilters'
import type { SheetFrame, SheetPair } from './api'

function frameLabel(frame: SheetFrame | null | undefined): string {
  if (!frame) return ''
  return frame.sheet_no ?? frame.sheet_title ?? frame.norm_key
}

// Hoisted out of JSX for the same reason `SetScreen.tsx` hoists its own
// `labelKey` constants: `i18next/no-literal-string` validates every literal
// string prop on a custom component, not just user-facing JSX text.
const BEFORE_CANDIDATES_LABEL_KEY = 'compare.sheets.manualPairDialog.beforeLabel'
const AFTER_CANDIDATES_LABEL_KEY = 'compare.sheets.manualPairDialog.afterLabel'

interface CandidateListProps {
  labelKey: string
  candidates: SheetPair[]
  frameOf: (pair: SheetPair) => SheetFrame | null | undefined
  frameIdOf: (pair: SheetPair) => string | null | undefined
  selected: string | null
  onSelect: (frameId: string) => void
}

function CandidateList({ labelKey, candidates, frameOf, frameIdOf, selected, onSelect }: CandidateListProps) {
  const { t } = useTranslation()
  return (
    <div className="flex-1">
      <p className="mb-1 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
        {t(labelKey)}
      </p>
      {candidates.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--muted)' }}>
          {t('compare.sheets.manualPairDialog.empty')}
        </p>
      ) : (
        <ul className="hc-panel-2 max-h-40 overflow-y-auto">
          {candidates.map((pair) => {
            const frameId = frameIdOf(pair)
            if (!frameId) return null
            return (
              <li key={pair.id}>
                <button
                  type="button"
                  className="w-full px-2 py-1 text-left text-xs"
                  style={{
                    backgroundColor: frameId === selected ? 'var(--panel)' : 'transparent',
                    color: frameId === selected ? 'var(--accent-2)' : 'var(--text)',
                  }}
                  onClick={() => {
                    onSelect(frameId)
                  }}
                >
                  {frameLabel(frameOf(pair))}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

/**
 * Screen B's manual-pair dialog (brief Goal 5: "'짝 없음' 행에서 수동 짝
 * 맞춤 다이얼로그(전에만 있는 도곽 목록 ↔ 후에만 있는 도곽 목록 선택 →
 * `createManualPair`)"). Candidate lists are the whole sheet list's
 * before-only / after-only frames (not just the triggering row's own pair)
 * -- `unmatchedFrameCandidates` (`pairFilters.ts`) so a `removed` sheet on
 * one side can be paired with an `added` sheet on the other, which is
 * exactly R1-07's S14 fixture scenario this screen's e2e note names.
 */
export function ManualPairDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const pairs = useCompareStore((state) => state.pairs)
  const createManualPair = useCompareStore((state) => state.createManualPair)
  const busy = useCompareStore((state) => state.busy)

  const [beforeFrameId, setBeforeFrameId] = useState<string | null>(null)
  const [afterFrameId, setAfterFrameId] = useState<string | null>(null)

  const beforeCandidates = unmatchedFrameCandidates(pairs, 'before')
  const afterCandidates = unmatchedFrameCandidates(pairs, 'after')

  const confirm = async (): Promise<void> => {
    if (!beforeFrameId || !afterFrameId) return
    await createManualPair(beforeFrameId, afterFrameId)
    onClose()
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="manual-pair-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="hc-panel w-[480px] p-4 text-sm">
        <h2 id="manual-pair-title" className="mb-1 text-sm font-semibold">
          {t('compare.sheets.manualPairDialog.title')}
        </h2>
        <p className="mb-3 text-xs" style={{ color: 'var(--muted)' }}>
          {t('compare.sheets.manualPairDialog.description')}
        </p>

        <div className="mb-3 flex gap-3">
          <CandidateList
            labelKey={BEFORE_CANDIDATES_LABEL_KEY}
            candidates={beforeCandidates}
            frameOf={(pair) => pair.before_frame}
            frameIdOf={(pair) => pair.before_frame_id}
            selected={beforeFrameId}
            onSelect={setBeforeFrameId}
          />
          <CandidateList
            labelKey={AFTER_CANDIDATES_LABEL_KEY}
            candidates={afterCandidates}
            frameOf={(pair) => pair.after_frame}
            frameIdOf={(pair) => pair.after_frame_id}
            selected={afterFrameId}
            onSelect={setAfterFrameId}
          />
        </div>

        <div className="flex justify-end gap-2">
          <button type="button" className="hc-btn" onClick={onClose}>
            {t('compare.common.cancel')}
          </button>
          <button
            type="button"
            className="hc-btn hc-btn-primary"
            disabled={!beforeFrameId || !afterFrameId || busy}
            onClick={() => {
              void confirm()
            }}
          >
            {t('compare.sheets.manualPairDialog.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
