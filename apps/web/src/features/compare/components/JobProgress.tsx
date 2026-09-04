import { useTranslation } from 'react-i18next'
import type { CompareJobState } from '../../../state/compare'

/**
 * Job progress bar (brief R1-05 Goal 4: "잡 진행 바(단계·n/N·파일 이름)").
 * `job.message` is the engine's own progress string (contract §6.2 /
 * `docs/dev/compare-ingest.md`: e.g. `"convert 3/5 before A-101.dwg"`) --
 * not translated, the same way other screens show a raw engine error
 * message verbatim (`features/xref/UnresolvedXrefDialog.tsx`) -- it already
 * carries the n/N and file name the brief asks for; only the stage gets a
 * Korean label of its own.
 */
const STAGE_LABEL_KEYS: Record<string, string> = {
  convert: 'compare.set.job.stage.convert',
  crosscheck: 'compare.set.job.stage.crosscheck',
}

export function JobProgress({ job }: { job: CompareJobState }) {
  const { t } = useTranslation()
  const percent = Math.round(job.progress * 100)
  const stageKey = job.stage ? STAGE_LABEL_KEYS[job.stage] : undefined

  return (
    <div className="hc-panel p-3 text-xs" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
      <div className="mb-1 flex items-center justify-between" style={{ color: 'var(--muted)' }}>
        <span>{stageKey ? t(stageKey) : job.stage}</span>
        <span>{percent}%</span>
      </div>
      <div className="hc-progress">
        <span style={{ width: `${String(percent)}%` }} />
      </div>
      {job.message && (
        <p className="mt-1 truncate font-mono" style={{ color: 'var(--muted)' }}>
          {job.message}
        </p>
      )}
    </div>
  )
}
