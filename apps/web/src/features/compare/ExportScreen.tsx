import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { registerHaloTestHook } from '../../test-hooks'
import { useCompareStore } from '../../state/compare'
import { useExportStore } from '../../state/export'
import { JobProgress } from './components/JobProgress'
import { getClusters } from './reviewApi'
import type { SheetPair } from './api'
import type { OutputWriter, RunOutputFile } from './exportApi'

/**
 * Screen D 출력 (brief R1-10): shows what will be exported (승인·무시
 * counts, scope, the DWG/DXF choice the engine already made from the ZWCAD
 * chip, the run date), starts `POST .../export`, and once it finishes shows
 * the produced files, the output folder and the two follow-up actions
 * ("폴더 열기", "변경 리스트 TSV 복사").
 *
 * The result table renders `Run` fields only (brief Constraints: "출력 결과
 * 표시는 Run 스키마 필드만. 렌더러가 파일을 읽지 않는다") -- including its
 * own "경고" column, which is derived purely from each file's own
 * `format`/`writer` (a `dxf-only` writer *is* the ZWCAD-unavailable/failed
 * warning; `docs/dev/compare-export.md`'s "DWG 저장 경로 선택" table) rather
 * than a second fetch of `compare_set.stats.export.warnings` (out of scope
 * for this file's schema-shaped display; see the report's "Decisions").
 */

registerHaloTestHook('compareRunExport', async ({ runDate }: { runDate: string }) => {
  const compareSetId = useCompareStore.getState().compareSetId
  if (!compareSetId) throw new Error('compareRunExport: no compare_set_id (call compareStartSet first)')
  await useExportStore.getState().runExport({ compareSetId, runDate })
  const state = useExportStore.getState()
  if (state.error) throw new Error(state.error)
  if (!state.run) throw new Error('compareRunExport: export finished with no run')
  return state.run
})

registerHaloTestHook('compareGetLastRun', () => useExportStore.getState().run)

interface ExportPreview {
  approved: number
  ignored: number
  targetSheets: number
}

/** The pairs the engine would actually try to export (`docs/dev/compare-
 * export.md`'s "대상 고르기": added/removed/unrecognized/converter_mismatch
 * pairs and pairs with no compare DXF are skipped) -- an approximation good
 * enough for a pre-run preview, not the engine's own selection. */
function candidatePairs(pairs: SheetPair[]): SheetPair[] {
  return pairs.filter((pair) => pair.cluster_count > 0 && Boolean(pair.compare_dxf_path))
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Sums each candidate pair's cluster sidecar counts (brief Goal 1: "요약
 * (승인 n건 / 무시 n건 / 대상 도곽 n장)"). Nothing else on screen D reads a
 * sidecar -- `GET .../clusters` is the same call screen C already makes, not
 * a new kind of read. A pair whose sidecar fails to load (e.g. it was never
 * actually compared) is silently excluded rather than failing the whole
 * preview. */
async function loadExportPreview(pairs: SheetPair[]): Promise<ExportPreview> {
  const candidates = candidatePairs(pairs)
  const sidecars = await Promise.all(candidates.map((pair) => getClusters(pair.id).catch(() => null)))

  let approved = 0
  let ignored = 0
  let targetSheets = 0
  for (const sidecar of sidecars) {
    if (!sidecar) continue
    approved += sidecar.counts.approved
    ignored += sidecar.counts.ignored
    if (sidecar.counts.approved > 0) targetSheets += 1
  }
  return { approved, ignored, targetSheets }
}

const WRITER_LABEL_KEYS: Record<OutputWriter, string> = {
  'zwcad-com': 'compare.export.writer.zwcadCom',
  'acad-ts': 'compare.export.writer.acadTs',
  'dxf-only': 'compare.export.writer.dxfOnly',
}

export function ExportScreen() {
  const { t } = useTranslation()
  const compareSetId = useCompareStore((state) => state.compareSetId)
  const summary = useCompareStore((state) => state.summary)
  const pairs = useCompareStore((state) => state.pairs)
  const zwcad = useCompareStore((state) => state.zwcad)
  const goto = useCompareStore((state) => state.goto)

  const runDate = useExportStore((state) => state.runDate)
  const run = useExportStore((state) => state.run)
  const exportJob = useExportStore((state) => state.exportJob)
  const busy = useExportStore((state) => state.busy)
  const error = useExportStore((state) => state.error)
  const toast = useExportStore((state) => state.toast)
  const setRunDate = useExportStore((state) => state.setRunDate)
  const runExport = useExportStore((state) => state.runExport)
  const copyTsv = useExportStore((state) => state.copyTsv)
  const openOutput = useExportStore((state) => state.openOutput)
  const cancelActiveJob = useExportStore((state) => state.cancelActiveJob)

  const [preview, setPreview] = useState<ExportPreview | null>(null)
  const [previewError, setPreviewError] = useState<string | null>(null)

  // Screen D's own run-date field starts at the compare set's `run_date`
  // (contract §9) -- re-initialised only when the set itself changes, not on
  // every `refreshSummary()` poll, so it does not stomp on an edit the user
  // just made.
  useEffect(() => {
    if (summary) setRunDate(summary.run_date)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see comment above: keyed on the set id on purpose.
  }, [summary?.id])

  useEffect(() => {
    let cancelled = false
    loadExportPreview(pairs)
      .then((result) => {
        if (cancelled) return
        setPreview(result)
        setPreviewError(null)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setPreview(null)
        setPreviewError(errorMessage(err))
      })
    return () => {
      cancelled = true
    }
  }, [pairs])

  // Contract Constraints: "잡 폴링은 화면을 떠나도 새지 않게 정리".
  useEffect(() => {
    return () => {
      cancelActiveJob()
    }
  }, [cancelActiveJob])

  const methodLabelKey = zwcad?.available ? 'compare.export.method.zwcad' : 'compare.export.method.dxf'
  const canRun = compareSetId !== null && runDate !== '' && !busy

  function startExport(): void {
    if (!compareSetId) return
    void runExport({ compareSetId, runDate })
  }

  return (
    <main data-testid="export-screen" className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-sm font-semibold">{t('compare.export.title')}</h1>
        <button
          type="button"
          className="hc-btn"
          onClick={() => {
            goto('sheets')
          }}
        >
          {t('compare.export.back')}
        </button>
      </div>

      <section className="hc-panel p-3 text-xs">
        <h2 className="mb-2 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
          {t('compare.export.summary.title')}
        </h2>
        {previewError && (
          <p className="hc-error" role="alert">
            {previewError}
          </p>
        )}
        {preview ? (
          <p style={{ color: 'var(--text)' }}>
            {t('compare.export.summary.counts', {
              approved: preview.approved,
              ignored: preview.ignored,
              sheets: preview.targetSheets,
            })}
          </p>
        ) : (
          !previewError && <p style={{ color: 'var(--muted)' }}>{t('compare.common.loading')}</p>
        )}
      </section>

      <div className="flex flex-wrap items-end gap-4">
        <div className="hc-panel p-3 text-xs">
          <p className="mb-1" style={{ color: 'var(--muted)' }}>
            {t('compare.export.scope.label')}
          </p>
          <p style={{ color: 'var(--text)' }}>{t('compare.export.scope.all')}</p>
        </div>

        <div className="hc-panel p-3 text-xs">
          <p className="mb-1" style={{ color: 'var(--muted)' }}>
            {t('compare.export.method.label')}
          </p>
          <p style={{ color: 'var(--text)' }}>{t(methodLabelKey)}</p>
        </div>

        <label className="hc-panel flex flex-col gap-1 p-3 text-xs" htmlFor="export-run-date">
          <span style={{ color: 'var(--muted)' }}>{t('compare.export.runDate.label')}</span>
          <input
            id="export-run-date"
            type="date"
            className="hc-input"
            value={runDate}
            disabled={busy}
            onChange={(event) => {
              setRunDate(event.target.value)
            }}
          />
        </label>

        <button type="button" className="hc-btn hc-btn-primary ml-auto" disabled={!canRun} onClick={startExport}>
          {busy ? t('compare.export.running') : t('compare.export.run')}
        </button>
      </div>

      {toast && (
        <div className="hc-toast flex items-center justify-between" role="status">
          <span>{t(toast)}</span>
        </div>
      )}

      {error && (
        <div className="hc-error flex items-center justify-between" role="alert">
          <span>{error}</span>
          <button type="button" className="hc-btn" onClick={startExport}>
            {t('compare.common.retry')}
          </button>
        </div>
      )}

      {exportJob && <JobProgress job={exportJob} />}

      {run && (
        <section className="hc-panel p-3 text-xs" data-testid="export-result">
          <h2 className="mb-2 text-xs font-semibold" style={{ color: 'var(--muted)' }}>
            {t('compare.export.result.title')}
          </h2>
          <p className="mb-2 truncate font-mono" style={{ color: 'var(--text)' }}>
            {run.output_dir}
          </p>

          <table className="hc-table" role="table">
            <thead>
              <tr>
                <th scope="col">{t('compare.export.result.sheetNo')}</th>
                <th scope="col">{t('compare.export.result.file')}</th>
                <th scope="col">{t('compare.export.result.format')}</th>
                <th scope="col">{t('compare.export.result.writer')}</th>
                <th scope="col">{t('compare.export.result.warning')}</th>
              </tr>
            </thead>
            <tbody>
              {run.files.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center" style={{ color: 'var(--muted)' }}>
                    {t('compare.export.result.empty')}
                  </td>
                </tr>
              ) : (
                run.files.map((file) => <ResultRow key={file.pair_id} file={file} />)
              )}
            </tbody>
          </table>

          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              className="hc-btn"
              onClick={() => {
                void openOutput()
              }}
            >
              {t('compare.export.openFolder')}
            </button>
            <button
              type="button"
              className="hc-btn"
              onClick={() => {
                void copyTsv()
              }}
            >
              {t('compare.export.copyTsv')}
            </button>
            <button
              type="button"
              className="hc-btn ml-auto"
              onClick={() => {
                goto('sheets')
              }}
            >
              {t('compare.export.backToList')}
            </button>
          </div>
        </section>
      )}
    </main>
  )
}

function ResultRow({ file }: { file: RunOutputFile }) {
  const { t } = useTranslation()
  const warningKey = file.writer === 'dxf-only' ? 'compare.export.warning.dxfOnly' : null

  return (
    <tr>
      <td className="font-mono">{file.sheet_no ?? '-'}</td>
      <td className="truncate font-mono">{file.path}</td>
      <td>{file.format.toUpperCase()}</td>
      <td style={{ color: 'var(--muted)' }}>{t(WRITER_LABEL_KEYS[file.writer])}</td>
      <td style={{ color: warningKey ? 'var(--warn)' : 'var(--muted)' }}>{warningKey ? t(warningKey) : '-'}</td>
    </tr>
  )
}
