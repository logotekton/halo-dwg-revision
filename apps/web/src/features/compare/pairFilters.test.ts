import { describe, expect, it } from 'vitest'
import { countByStatus, filterAndSortPairs, unmatchedFrameCandidates } from './pairFilters'
import type { SheetFrame, SheetPair } from './api'

function frame(overrides: Partial<SheetFrame> = {}): SheetFrame {
  return {
    id: 'f',
    compare_set_id: 'cs1',
    role: 'before',
    file_id: 'file1',
    kind: 'titleblock',
    bbox: [0, 0, 100, 100],
    norm_key: 'A-101',
    sort_index: 0,
    ...overrides,
  }
}

function pair(overrides: Partial<SheetPair> = {}): SheetPair {
  return {
    id: 'p1',
    compare_set_id: 'cs1',
    before_frame_id: 'f1',
    after_frame_id: 'f2',
    status: 'changed',
    sort_key: 'A-101',
    change_count: 0,
    minor_count: 0,
    cluster_count: 0,
    ...overrides,
  }
}

describe('countByStatus', () => {
  it('counts every status plus a running "all" total', () => {
    const pairs = [pair({ status: 'changed' }), pair({ status: 'same' }), pair({ status: 'changed' })]
    const counts = countByStatus(pairs)

    expect(counts.all).toBe(3)
    expect(counts.changed).toBe(2)
    expect(counts.same).toBe(1)
    expect(counts.added).toBe(0)
  })
})

describe('filterAndSortPairs', () => {
  const pairs = [
    pair({ id: 'p-a102', sort_key: 'A-102', change_count: 1, status: 'changed', before_frame: frame({ sheet_no: 'A-102', sheet_title: 'ROOF' }) }),
    pair({ id: 'p-a101', sort_key: 'A-101', change_count: 5, status: 'changed', before_frame: frame({ sheet_no: 'A-101', sheet_title: 'PLAN' }) }),
    pair({ id: 'p-a103', sort_key: 'A-103', change_count: 0, status: 'same', before_frame: frame({ sheet_no: 'A-103', sheet_title: 'SECTION' }) }),
  ]

  it('filters by status, "all" keeping every row', () => {
    const changed = filterAndSortPairs(pairs, { status: 'changed', q: '', sort: 'sort_key' })
    expect(changed.map((p) => p.id)).toEqual(['p-a101', 'p-a102'])

    const all = filterAndSortPairs(pairs, { status: 'all', q: '', sort: 'sort_key' })
    expect(all).toHaveLength(3)
  })

  it('sorts by sort_key (ascending) or change_count (descending)', () => {
    const byKey = filterAndSortPairs(pairs, { status: 'all', q: '', sort: 'sort_key' })
    expect(byKey.map((p) => p.sort_key)).toEqual(['A-101', 'A-102', 'A-103'])

    const byChanges = filterAndSortPairs(pairs, { status: 'all', q: '', sort: 'change_count' })
    expect(byChanges.map((p) => p.change_count)).toEqual([5, 1, 0])
  })

  it('searches sheet_no and sheet_title case-insensitively', () => {
    const byNumber = filterAndSortPairs(pairs, { status: 'all', q: 'a-101', sort: 'sort_key' })
    expect(byNumber.map((p) => p.id)).toEqual(['p-a101'])

    const byTitle = filterAndSortPairs(pairs, { status: 'all', q: 'section', sort: 'sort_key' })
    expect(byTitle.map((p) => p.id)).toEqual(['p-a103'])
  })

  it('an empty query matches everything', () => {
    expect(filterAndSortPairs(pairs, { status: 'all', q: '   ', sort: 'sort_key' })).toHaveLength(3)
  })
})

describe('unmatchedFrameCandidates', () => {
  it('lists before-only frames for role "before" (removed or half-unpaired)', () => {
    const pairs = [
      pair({ id: 'removed', status: 'removed', before_frame_id: 'f1', after_frame_id: null }),
      pair({ id: 'added', status: 'added', before_frame_id: null, after_frame_id: 'f2' }),
      pair({ id: 'changed', status: 'changed', before_frame_id: 'f3', after_frame_id: 'f4' }),
    ]

    expect(unmatchedFrameCandidates(pairs, 'before').map((p) => p.id)).toEqual(['removed'])
    expect(unmatchedFrameCandidates(pairs, 'after').map((p) => p.id)).toEqual(['added'])
  })
})
