import { useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useCompareStore, type CompareState } from '../../state/compare'
import { loadViewerHost, REVIEW_CANVAS_ID, useReviewStore } from '../../state/review'
import { StatusChip } from './components/StatusChip'
import { filterAndSortPairs } from './pairFilters'
import { ClusterList } from './review/ClusterList'
import { MinorList } from './review/MinorList'
import { registerReviewTestHooks } from './review/testHooks'
import { ViewModeBar } from './review/ViewModeBar'
import type { SheetPair } from './api'

/**
 * Screen C 검토 (brief R1-08): the compare DXF on the left, its cloud marks on
 * the right.
 *
 * Everything drawn here was computed by the engine (`clusters.json` +
 * `compare.dxf`); the screen only chooses what to show -- the view mode is a
 * layer-visibility change, the number badge is a camera move, and 승인·무시·
 * 문구 are three fields of one `PATCH` (`docs/contracts/compare-dxf.md` §9).
 */

registerReviewTestHooks()

/** The pairs `[` / `]` walk, in screen B's own filtered/sorted order (brief
 * Goal 5). Pairs with no compare DXF were never compared, so there is nothing
 * for screen C to open on them. */
function navigablePairs(state: Pick<CompareState, 'pairs' | 'filters'>): SheetPair[] {
  return filterAndSortPairs(state.pairs, state.filters).filter((pair) => pair.compare_dxf_path)
}

function stepPair(delta: number): void {
  const compare = useCompareStore.getState()
  const pairs = navigablePairs(compare)
  const index = pairs.findIndex((pair) => pair.id === compare.selectedPairId)
  if (index < 0) return
  const next = pairs[index + delta]
  if (next) compare.openPair(next.id)
}

export function ReviewScreen() {
  const { t } = useTranslation()

  const pairs = useCompareStore((state) => state.pairs)
  const filters = useCompareStore((state) => state.filters)
  const selectedPairId = useCompareStore((state) => state.selectedPairId)
  const goto = useCompareStore((state) => state.goto)

  const sidecar = useReviewStore((state) => state.sidecar)
  const viewMode = useReviewStore((state) => state.viewMode)
  const selectedCluster = useReviewStore((state) => state.selectedCluster)
  const showMinor = useReviewStore((state) => state.showMinor)
  const loading = useReviewStore((state) => state.loading)
  const error = useReviewStore((state) => state.error)
  const renderError = useReviewStore((state) => state.renderError)
  const visibleLayers = useReviewStore((state) => state.visibleLayers)

  const loadPair = useReviewStore((state) => state.loadPair)
  const select = useReviewStore((state) => state.select)
  const selectByHandles = useReviewStore((state) => state.selectByHandles)
  const decide = useReviewStore((state) => state.decide)
  const setLabel = useReviewStore((state) => state.setLabel)
  const setNote = useReviewStore((state) => state.setNote)
  const setViewMode = useReviewStore((state) => state.setViewMode)
  const toggleMinor = useReviewStore((state) => state.toggleMinor)

  const navigable = useMemo(() => navigablePairs({ pairs, filters }), [pairs, filters])
  const index = navigable.findIndex((pair) => pair.id === selectedPairId)
  const hasPrev = index > 0
  const hasNext = index >= 0 && index < navigable.length - 1
  const pair = pairs.find((item) => item.id === selectedPairId) ?? null
  const sheetNo = pair?.after_frame?.sheet_no ?? pair?.before_frame?.sheet_no ?? null
  const sheetTitle = pair?.after_frame?.sheet_title ?? pair?.before_frame?.sheet_title ?? ''

  const clusters = sidecar?.clusters ?? []
  const approved = clusters.filter((cluster) => cluster.decision === 'approved').length
  const ignored = clusters.filter((cluster) => cluster.decision === 'ignored').length

  // The pair to show comes from `state/compare.ts` (screen B's selection, the
  // `[`/`]` buttons and the `compareOpenPair` hook all set it), so one effect
  // keyed on it is the single place a sheet is loaded.
  useEffect(() => {
    if (selectedPairId) void loadPair(selectedPairId)
  }, [selectedPairId, loadPair])

  // Hit test -> `handle_to_cluster` -> selection (contract §9). Subscribed
  // here rather than in the store so it lives exactly as long as the screen;
  // `host.ts` keeps its subscriber set at module scope, so subscribing before
  // (or after) the drawing exists is safe.
  useEffect(() => {
    let dispose: (() => void) | null = null
    let cancelled = false
    void loadViewerHost().then((host) => {
      if (cancelled) return
      dispose = host.onSelection(selectByHandles)
    })
    return () => {
      cancelled = true
      dispose?.()
    }
  }, [selectByHandles])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target?.isContentEditable) return
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return

      const review = useReviewStore.getState()
      const current = review.selectedCluster
      switch (event.key) {
        case 'a':
        case 'A':
          if (current !== null) void review.decide(current, 'approved')
          break
        case 'x':
        case 'X':
          if (current !== null) void review.decide(current, 'ignored')
          break
        case 'j':
        case 'J':
          review.selectStep(1)
          break
        case 'k':
        case 'K':
          review.selectStep(-1)
          break
        case '[':
          stepPair(-1)
          break
        case ']':
          stepPair(1)
          break
        default:
          return
      }
      event.preventDefault()
    }

    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [])

  return (
    <main data-testid="review-screen" className="flex flex-1 flex-col overflow-hidden p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="hc-btn"
          onClick={() => {
            goto('sheets')
          }}
        >
          {t('compare.review.back')}
        </button>

        <button
          type="button"
          className="hc-btn"
          disabled={!hasPrev}
          aria-label={t('compare.review.prevPair')}
          onClick={() => {
            stepPair(-1)
          }}
        >
          {t('compare.review.prevPair')}
        </button>
        <button
          type="button"
          className="hc-btn"
          disabled={!hasNext}
          aria-label={t('compare.review.nextPair')}
          onClick={() => {
            stepPair(1)
          }}
        >
          {t('compare.review.nextPair')}
        </button>

        <h1 className="font-mono text-sm font-semibold">{sheetNo ?? t('compare.review.sheetUnknown')}</h1>
        <span className="text-xs" style={{ color: 'var(--muted)' }}>
          {sheetTitle}
        </span>
        {pair && <StatusChip status={pair.status} />}

        <div className="ml-auto flex items-center gap-2">
          <ViewModeBar
            mode={viewMode}
            onChange={(mode) => {
              void setViewMode(mode)
            }}
          />
        </div>
      </div>

      {error && (
        <p className="hc-error mb-2" role="alert">
          {error}
        </p>
      )}

      <div className="flex min-h-0 flex-1 gap-3">
        <div className="hc-panel relative min-w-0 flex-1 overflow-hidden">
          <div
            id={REVIEW_CANVAS_ID}
            data-testid="review-canvas"
            data-cmp-visible={visibleLayers.join(',')}
            aria-label={t('compare.review.canvasLabel')}
            className="absolute inset-0"
            style={{ backgroundColor: '#000000' }}
          />
          {loading && (
            <p className="pointer-events-none relative p-2 text-xs" style={{ color: 'var(--muted)' }}>
              {t('compare.review.loading')}
            </p>
          )}
          {renderError && (
            <p className="hc-error relative m-2" role="alert" data-testid="review-render-error">
              {t('compare.review.renderFailed', { message: renderError })}
            </p>
          )}
        </div>

        <aside className="hc-panel flex w-96 shrink-0 flex-col overflow-hidden p-2">
          {selectedPairId === null ? (
            <p className="text-xs" style={{ color: 'var(--muted)' }}>
              {t('compare.review.noPair')}
            </p>
          ) : (
            <>
              <p className="mb-2 text-xs" style={{ color: 'var(--muted)' }}>
                {t('compare.review.summary', { clusters: clusters.length, approved, ignored })}
              </p>
              <div className="min-h-0 flex-1 overflow-y-auto">
                <ClusterList
                  clusters={clusters}
                  selected={selectedCluster}
                  onSelect={select}
                  onDecide={(number, decision) => {
                    void decide(number, decision)
                  }}
                  onLabel={(number, text) => {
                    void setLabel(number, text)
                  }}
                  onNote={(number, text) => {
                    void setNote(number, text)
                  }}
                />
                <MinorList changes={sidecar?.changes ?? []} expanded={showMinor} onToggle={toggleMinor} />
              </div>
              <p className="mt-2 text-xs" style={{ color: 'var(--muted)' }}>
                {t('compare.review.shortcuts')}
              </p>
            </>
          )}
        </aside>
      </div>
    </main>
  )
}
