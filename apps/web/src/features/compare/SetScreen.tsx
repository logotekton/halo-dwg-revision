import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useCompareStore } from '../../state/compare'
import { JobProgress } from './components/JobProgress'
import { ZwcadChip } from './components/ZwcadChip'
import type { CompareFileEntry, CompareSetSummary } from './api'

const FAILED_STATUSES = new Set(['FAILED', 'NEEDS_MANUAL_CONVERSION'])

// i18n keys passed to custom-component props further down, hoisted out of
// JSX -- `i18next/no-literal-string` (mode "jsx-only") validates every
// literal string prop on a *custom* component (unlike a native DOM tag,
// where only title/aria-label/placeholder/alt/value are checked), so a
// literal key string passed as e.g. `labelKey="..."` is flagged the same
// as literal user-facing JSX text would be. A module-scope identifier
// (outside any JSX) sidesteps that check the same way `pairFilters.ts`'s
// `STATUS_FILTER_ORDER` does for `<StatusFilterChip status={...}>`.
const BEFORE_FOLDER_LABEL_KEY = 'compare.set.beforeFolder.label'
const AFTER_FOLDER_LABEL_KEY = 'compare.set.afterFolder.label'
const BEFORE_SIDE_LABEL_KEY = 'compare.common.before'
const AFTER_SIDE_LABEL_KEY = 'compare.common.after'

function failedFiles(files: CompareFileEntry[]): CompareFileEntry[] {
  return files.filter((file) => FAILED_STATUSES.has(file.import_status))
}

interface FolderPanelProps {
  labelKey: string
  dir: string | null
  onPick: () => void
  busy: boolean
}

function FolderPanel({ labelKey, dir, onPick, busy }: FolderPanelProps) {
  const { t } = useTranslation()
  return (
    <div className="hc-panel flex-1 p-3">
      <p className="mb-2 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
        {t(labelKey)}
      </p>
      <p className="mb-3 truncate font-mono text-xs" style={{ color: dir ? 'var(--text)' : 'var(--muted)' }}>
        {dir ?? t('compare.set.folderEmpty')}
      </p>
      <button type="button" className="hc-btn" disabled={busy} onClick={onPick}>
        {t('compare.set.pickFolder')}
      </button>
    </div>
  )
}

/**
 * Screen A (brief R1-05 Goal 4): folder pickers, run date, ZWCAD chip,
 * "인입 시작" → ingest job progress → automatic `startFrames` → screen B,
 * plus the ingest summary card once one exists.
 */
export function SetScreen() {
  const { t } = useTranslation()
  const beforeDir = useCompareStore((state) => state.beforeDir)
  const afterDir = useCompareStore((state) => state.afterDir)
  const runDate = useCompareStore((state) => state.runDate)
  const summary = useCompareStore((state) => state.summary)
  const files = useCompareStore((state) => state.files)
  const job = useCompareStore((state) => state.job)
  const zwcad = useCompareStore((state) => state.zwcad)
  const toast = useCompareStore((state) => state.toast)
  const error = useCompareStore((state) => state.error)
  const busy = useCompareStore((state) => state.busy)

  const pickBefore = useCompareStore((state) => state.pickBefore)
  const pickAfter = useCompareStore((state) => state.pickAfter)
  const setRunDate = useCompareStore((state) => state.setRunDate)
  const loadZwcadStatus = useCompareStore((state) => state.loadZwcadStatus)
  const startSet = useCompareStore((state) => state.startSet)
  const dismissToast = useCompareStore((state) => state.dismissToast)
  const cancelActiveJob = useCompareStore((state) => state.cancelActiveJob)

  useEffect(() => {
    void loadZwcadStatus()
  }, [loadZwcadStatus])

  // Contract Constraints: "잡 폴링은 화면을 떠나도 새지 않게 정리".
  useEffect(() => {
    return () => {
      cancelActiveJob()
    }
  }, [cancelActiveJob])

  const canStart = beforeDir !== null && afterDir !== null && !busy

  return (
    <main data-testid="set-screen" className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-sm font-semibold">{t('compare.set.title')}</h1>
        {zwcad && <ZwcadChip status={zwcad} />}
      </div>

      <div className="flex gap-4">
        <FolderPanel
          labelKey={BEFORE_FOLDER_LABEL_KEY}
          dir={beforeDir}
          busy={busy}
          onPick={() => {
            void pickBefore()
          }}
        />
        <FolderPanel
          labelKey={AFTER_FOLDER_LABEL_KEY}
          dir={afterDir}
          busy={busy}
          onPick={() => {
            void pickAfter()
          }}
        />
      </div>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-xs" style={{ color: 'var(--muted)' }} htmlFor="compare-run-date">
          {t('compare.set.runDate.label')}
          <input
            id="compare-run-date"
            type="date"
            className="hc-input"
            value={runDate}
            disabled={busy}
            onChange={(event) => {
              setRunDate(event.target.value)
            }}
          />
        </label>

        <button
          type="button"
          className="hc-btn hc-btn-primary ml-auto"
          disabled={!canStart}
          onClick={() => {
            void startSet()
          }}
        >
          {busy ? t('compare.set.starting') : t('compare.set.start')}
        </button>
      </div>

      {toast && (
        <div className="hc-toast flex items-center justify-between" role="status">
          <span>{t(toast)}</span>
          <button type="button" className="hc-btn" onClick={dismissToast}>
            {t('compare.common.dismiss')}
          </button>
        </div>
      )}

      {error && (
        <p className="hc-error" role="alert">
          {error}
        </p>
      )}

      {job && <JobProgress job={job} />}

      {summary && <SummaryCard summary={summary} files={files} />}
    </main>
  )
}

function SummaryCard({ summary, files }: { summary: CompareSetSummary; files: CompareFileEntry[] }) {
  const { t } = useTranslation()
  const failed = failedFiles(files)

  return (
    <section className="hc-panel p-3 text-xs">
      <h2 className="mb-2 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
        {t('compare.set.summary.title')}
      </h2>
      <div className="grid grid-cols-2 gap-3">
        <SideSummary labelKey={BEFORE_SIDE_LABEL_KEY} side={summary.before} />
        <SideSummary labelKey={AFTER_SIDE_LABEL_KEY} side={summary.after} />
      </div>

      {summary.converter.mismatch_files > 0 && (
        <p className="mt-2" style={{ color: 'var(--danger)' }}>
          {t('compare.set.summary.converterMismatch', { count: summary.converter.mismatch_files })}
        </p>
      )}

      {summary.fonts_missing.length > 0 && (
        <p className="mt-2" style={{ color: 'var(--warn)' }}>
          {t('compare.set.summary.fontsMissing', { fonts: summary.fonts_missing.join(', ') })}
        </p>
      )}

      <p className="mt-2" style={{ color: 'var(--muted)' }}>
        {summary.crosscheck
          ? t('compare.set.summary.crosscheck', {
              sampled: summary.crosscheck.sampled,
              mismatched: summary.crosscheck.mismatched,
            })
          : t('compare.set.summary.crosscheckNone')}
      </p>

      {failed.length > 0 && (
        <div className="mt-2">
          <h3 className="font-semibold" style={{ color: 'var(--danger)' }}>
            {t('compare.set.summary.failedFilesTitle')}
          </h3>
          <ul>
            {failed.map((file) => (
              <li key={file.id} className="truncate" style={{ color: 'var(--muted)' }}>
                {file.original_name}
                {file.error_message ? `: ${file.error_message}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function SideSummary({
  labelKey,
  side,
}: {
  labelKey: string
  side: { files: number; converted: number; failed: number; excluded: number }
}) {
  const { t } = useTranslation()
  return (
    <div>
      <p className="font-semibold" style={{ color: 'var(--text)' }}>
        {t(labelKey)}
      </p>
      <p style={{ color: 'var(--muted)' }}>{t('compare.set.summary.files', { count: side.files })}</p>
      <p style={{ color: 'var(--muted)' }}>{t('compare.set.summary.converted', { count: side.converted })}</p>
      <p style={{ color: 'var(--muted)' }}>{t('compare.set.summary.failed', { count: side.failed })}</p>
      <p style={{ color: 'var(--muted)' }}>{t('compare.set.summary.excluded', { count: side.excluded })}</p>
    </div>
  )
}
