import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useCompareStore } from '../../state/compare'
import { StatusChip } from './components/StatusChip'
import { ManualPairDialog } from './ManualPairDialog'
import { countByStatus, filterAndSortPairs, STATUS_FILTER_ORDER, type StatusFilter } from './pairFilters'
import type { SheetFrame, SheetPair } from './api'

const MANUAL_PAIR_CANDIDATE_STATUSES: ReadonlySet<SheetPair['status']> = new Set(['unpaired', 'added', 'removed'])

function frameCell(frame: SheetFrame | null | undefined): string {
  return frame?.date_text ?? '-'
}

function scaleCell(pair: SheetPair): string {
  return pair.before_frame?.scale_text ?? pair.after_frame?.scale_text ?? '-'
}

function matchMethodKey(pair: SheetPair): string | null {
  return pair.match_method ? `compare.sheets.matchMethod.${pair.match_method}` : null
}

/**
 * Screen B (brief R1-05 Goal 5): the sheet list table, status filter chips,
 * search, sort, the manual-pair dialog, and the three action buttons.
 */
export function SheetListScreen() {
  const { t } = useTranslation()
  const pairs = useCompareStore((state) => state.pairs)
  const pairsAvailable = useCompareStore((state) => state.pairsAvailable)
  const filters = useCompareStore((state) => state.filters)
  const selectedPairId = useCompareStore((state) => state.selectedPairId)
  const hasRunCompare = useCompareStore((state) => state.hasRunCompare)
  const busy = useCompareStore((state) => state.busy)
  const toast = useCompareStore((state) => state.toast)
  const error = useCompareStore((state) => state.error)
  const job = useCompareStore((state) => state.job)

  const setFilters = useCompareStore((state) => state.setFilters)
  const selectPair = useCompareStore((state) => state.selectPair)
  const openPair = useCompareStore((state) => state.openPair)
  const deletePair = useCompareStore((state) => state.deletePair)
  const startRun = useCompareStore((state) => state.startRun)
  const loadPairs = useCompareStore((state) => state.loadPairs)
  const goto = useCompareStore((state) => state.goto)
  const dismissToast = useCompareStore((state) => state.dismissToast)

  const [dialogOpen, setDialogOpen] = useState(false)

  const visiblePairs = useMemo(() => filterAndSortPairs(pairs, filters), [pairs, filters])
  const counts = useMemo(() => countByStatus(pairs), [pairs])
  const selectedPair = pairs.find((pair) => pair.id === selectedPairId) ?? null

  const canOpenPair = selectedPair !== null && selectedPair.compare_dxf_path !== null && !busy
  const canRun = pairs.length > 0 && !busy
  const canExportAll = hasRunCompare && !busy

  if (!pairsAvailable) {
    return (
      <main data-testid="sheets-screen" className="flex flex-1 flex-col items-center justify-center gap-3 p-4 text-xs">
        <p style={{ color: 'var(--muted)' }}>{t('compare.sheets.pairsUnavailable')}</p>
        <button
          type="button"
          className="hc-btn"
          onClick={() => {
            void loadPairs()
          }}
        >
          {t('compare.common.retry')}
        </button>
      </main>
    )
  }

  return (
    <main data-testid="sheets-screen" className="flex flex-1 flex-col gap-3 overflow-hidden p-4">
      <h1 className="text-sm font-semibold">{t('compare.sheets.title')}</h1>

      <div className="flex flex-wrap items-center gap-2">
        {STATUS_FILTER_ORDER.map((status) => (
          <StatusFilterChip
            key={status}
            status={status}
            count={counts[status]}
            active={filters.status === status}
            onClick={() => {
              setFilters({ status })
            }}
          />
        ))}

        <input
          type="search"
          className="hc-input ml-auto"
          aria-label={t('compare.sheets.searchLabel')}
          placeholder={t('compare.sheets.searchPlaceholder')}
          value={filters.q}
          onChange={(event) => {
            setFilters({ q: event.target.value })
          }}
        />

        <SortToggle sort={filters.sort} onChange={(sort) => { setFilters({ sort }) }} />
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
      {job && (
        <p className="text-xs" style={{ color: 'var(--muted)' }}>
          {t('compare.sheets.running')} {Math.round(job.progress * 100)}%
        </p>
      )}

      <div className="flex-1 overflow-y-auto">
        <table className="hc-table" role="table">
          <thead>
            <tr>
              <th scope="col">{t('compare.sheets.table.sheetNo')}</th>
              <th scope="col">{t('compare.sheets.table.sheetTitle')}</th>
              <th scope="col">{t('compare.sheets.table.before')}</th>
              <th scope="col">{t('compare.sheets.table.after')}</th>
              <th scope="col">{t('compare.sheets.table.changeCount')}</th>
              <th scope="col">{t('compare.sheets.table.matchMethod')}</th>
              <th scope="col">{t('compare.sheets.table.scale')}</th>
              <th scope="col">{t('compare.sheets.table.status')}</th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            {visiblePairs.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center" style={{ color: 'var(--muted)' }}>
                  {t('compare.sheets.table.empty')}
                </td>
              </tr>
            )}
            {visiblePairs.map((pair) => {
              const sheetNo = pair.before_frame?.sheet_no ?? pair.after_frame?.sheet_no ?? '-'
              const sheetTitle = pair.before_frame?.sheet_title ?? pair.after_frame?.sheet_title ?? '-'
              const methodKey = matchMethodKey(pair)
              return (
                <tr
                  key={pair.id}
                  data-selected={pair.id === selectedPairId}
                  onClick={() => {
                    selectPair(pair.id)
                  }}
                >
                  <td className="font-mono">{sheetNo}</td>
                  <td>{sheetTitle}</td>
                  <td className="font-mono">{frameCell(pair.before_frame)}</td>
                  <td className="font-mono">{frameCell(pair.after_frame)}</td>
                  <td className="font-mono">{pair.change_count}</td>
                  <td style={{ color: 'var(--muted)' }}>{methodKey ? t(methodKey) : '-'}</td>
                  <td className="font-mono">{scaleCell(pair)}</td>
                  <td>
                    <StatusChip status={pair.status} />
                  </td>
                  <td>
                    {pair.match_method === 'manual' ? (
                      <button
                        type="button"
                        className="hc-btn"
                        onClick={(event) => {
                          event.stopPropagation()
                          void deletePair(pair.id)
                        }}
                      >
                        {t('compare.sheets.unpair')}
                      </button>
                    ) : (
                      MANUAL_PAIR_CANDIDATE_STATUSES.has(pair.status) && (
                        <button
                          type="button"
                          className="hc-btn"
                          onClick={(event) => {
                            event.stopPropagation()
                            setDialogOpen(true)
                          }}
                        >
                          {t('compare.sheets.manualPair')}
                        </button>
                      )
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          className="hc-btn hc-btn-primary"
          disabled={!canRun}
          onClick={() => {
            void startRun()
          }}
        >
          {busy ? t('compare.sheets.running') : t('compare.sheets.runCompare')}
        </button>
        <button
          type="button"
          className="hc-btn"
          disabled={!canOpenPair}
          onClick={() => {
            if (selectedPairId) openPair(selectedPairId)
          }}
        >
          {t('compare.sheets.openPair')}
        </button>
        <button
          type="button"
          className="hc-btn ml-auto"
          disabled={!canExportAll}
          onClick={() => {
            goto('export')
          }}
        >
          {t('compare.sheets.exportAll')}
        </button>
      </div>

      {dialogOpen && <ManualPairDialog onClose={() => { setDialogOpen(false) }} />}
    </main>
  )
}

function StatusFilterChip({
  status,
  count,
  active,
  onClick,
}: {
  status: StatusFilter
  count: number
  active: boolean
  onClick: () => void
}) {
  const { t } = useTranslation()
  return (
    <button type="button" className="hc-chip" data-active={String(active)} onClick={onClick}>
      {t(`compare.sheets.filter.${status}`)} {count}
    </button>
  )
}

function SortToggle({
  sort,
  onChange,
}: {
  sort: 'sort_key' | 'change_count'
  onChange: (sort: 'sort_key' | 'change_count') => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-1" aria-label={t('compare.sheets.sort.label')} role="group">
      <button
        type="button"
        className="hc-chip"
        data-active={String(sort === 'sort_key')}
        onClick={() => { onChange('sort_key') }}
      >
        {t('compare.sheets.sort.sort_key')}
      </button>
      <button
        type="button"
        className="hc-chip"
        data-active={String(sort === 'change_count')}
        onClick={() => { onChange('change_count') }}
      >
        {t('compare.sheets.sort.change_count')}
      </button>
    </div>
  )
}
