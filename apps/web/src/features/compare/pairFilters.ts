import type { PairStatus, SheetPair } from './api'

/**
 * Pure, client-side filter/sort for screen B's sheet list (brief R1-05
 * Goal 5: "상태 필터 칩... 검색, 정렬"). Contract §7's `GET
 * /compare/sets/{id}/pairs?status=&q=&sort=` supports the same three
 * knobs server-side, but the sheet list is capped at 300 rows with no
 * pagination (brief "Defaults for ambiguity"), so re-fetching on every
 * keystroke/filter click would only add latency for no benefit -- `loadPairs`
 * fetches the full list once and this module reshapes it for display. This
 * is presentation filtering only (which already-computed rows to show),
 * not the matching/decision logic CLAUDE.md rule 4 reserves for the engine.
 */

export type StatusFilter = PairStatus | 'all'

export interface PairFilters {
  status: StatusFilter
  q: string
  sort: 'sort_key' | 'change_count'
}

export const DEFAULT_PAIR_FILTERS: PairFilters = { status: 'all', q: '', sort: 'sort_key' }

/** Fixed filter-chip order (brief Goal 5): 전체·변경·동일·신규·삭제·짝
 * 없음·미인식·변환기 불일치·대기. */
export const STATUS_FILTER_ORDER: StatusFilter[] = [
  'all',
  'changed',
  'same',
  'added',
  'removed',
  'unpaired',
  'unrecognized',
  'converter_mismatch',
  'pending',
]

function sheetLabel(pair: SheetPair): string {
  return pair.before_frame?.sheet_no ?? pair.after_frame?.sheet_no ?? ''
}

function sheetTitle(pair: SheetPair): string {
  return pair.before_frame?.sheet_title ?? pair.after_frame?.sheet_title ?? ''
}

function matchesQuery(pair: SheetPair, q: string): boolean {
  if (!q.trim()) return true
  const needle = q.trim().toLowerCase()
  return sheetLabel(pair).toLowerCase().includes(needle) || sheetTitle(pair).toLowerCase().includes(needle)
}

export function countByStatus(pairs: SheetPair[]): Record<StatusFilter, number> {
  const counts: Record<StatusFilter, number> = {
    all: pairs.length,
    pending: 0,
    changed: 0,
    same: 0,
    added: 0,
    removed: 0,
    unpaired: 0,
    unrecognized: 0,
    converter_mismatch: 0,
  }
  for (const pair of pairs) {
    counts[pair.status] += 1
  }
  return counts
}

export function filterAndSortPairs(pairs: SheetPair[], filters: PairFilters): SheetPair[] {
  const filtered = pairs.filter(
    (pair) => (filters.status === 'all' || pair.status === filters.status) && matchesQuery(pair, filters.q),
  )
  const sorted = [...filtered]
  if (filters.sort === 'change_count') {
    sorted.sort((a, b) => b.change_count - a.change_count || a.sort_key.localeCompare(b.sort_key))
  } else {
    sorted.sort((a, b) => a.sort_key.localeCompare(b.sort_key))
  }
  return sorted
}

/** Rows usable as one side of the manual-pair dialog (brief Goal 5: "전에만
 * 있는 도곽 목록 ↔ 후에만 있는 도곽 목록"): a frame on `role` with no
 * counterpart on the other side yet -- `removed`/`added` pairs always
 * qualify, and an `unpaired` pair qualifies from whichever side it does
 * carry a frame for. */
export function unmatchedFrameCandidates(pairs: SheetPair[], role: 'before' | 'after'): SheetPair[] {
  return pairs.filter((pair) => {
    if (role === 'before') return pair.before_frame_id != null && pair.after_frame_id == null
    return pair.after_frame_id != null && pair.before_frame_id == null
  })
}

export { sheetLabel, sheetTitle }
