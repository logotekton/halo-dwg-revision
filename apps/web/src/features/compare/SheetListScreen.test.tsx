import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { useCompareStore } from '../../state/compare'
import type { SheetFrame, SheetPair } from './api'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/** Indexes an array with a thrown (not `!`-asserted) error on a miss --
 * `@typescript-eslint/no-non-null-assertion` forbids `arr[i]!`. */
function nth<T>(items: T[], index: number): T {
  const item = items[index]
  if (item === undefined) throw new Error(`expected an element at index ${String(index)}`)
  return item
}

/** The `<tr>` containing the cell with this exact text, thrown (not
 * `!`-asserted) if `closest('tr')` finds none. */
function rowFor(text: string): HTMLElement {
  const row = screen.getByText(text).closest('tr')
  if (!row) throw new Error(`expected a <tr> ancestor of the "${text}" cell`)
  return row
}

const api = vi.hoisted(() => ({
  getPairs: vi.fn(),
  createManualPair: vi.fn(),
  deletePair: vi.fn(),
  startRun: vi.fn(),
  pollJob: vi.fn(),
}))

vi.mock('./api', () => ({
  createSet: vi.fn(),
  getSet: vi.fn(),
  getSetFiles: vi.fn(),
  getZwcadStatus: vi.fn(),
  startFrames: vi.fn(),
  getPairs: api.getPairs,
  createManualPair: api.createManualPair,
  deletePair: api.deletePair,
  startRun: api.startRun,
  pollJob: api.pollJob,
}))

vi.mock('./ipc', () => ({ pickFolder: vi.fn(), copyToClipboard: vi.fn(), openInOS: vi.fn() }))

const { SheetListScreen } = await import('./SheetListScreen')

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
    match_method: 'number',
    sort_key: 'A-101',
    change_count: 3,
    minor_count: 0,
    cluster_count: 1,
    compare_dxf_path: '/cs1/pair1/compare.dxf',
    ...overrides,
  }
}

describe('SheetListScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useCompareStore.setState(useCompareStore.getInitialState(), true)
  })

  afterEach(() => {
    cleanup()
  })

  it('shows a retry panel instead of the table when pairs are unavailable', () => {
    useCompareStore.setState({ pairsAvailable: false, pairs: [] })
    render(<SheetListScreen />)

    expect(screen.getByText('도곽 짝 맞춤 기능이 아직 준비되지 않았습니다')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders rows with status chips and filter chip counts', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      compareSetId: 'cs1',
      pairs: [
        pair({ id: 'p-101', status: 'changed', before_frame: frame({ sheet_no: 'A-101', sheet_title: '1층 평면도' }) }),
        pair({ id: 'p-102', status: 'same', change_count: 0, before_frame: frame({ sheet_no: 'A-102' }) }),
      ],
    })
    render(<SheetListScreen />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('A-101')).toBeInTheDocument()
    expect(screen.getByText('1층 평면도')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /전체 2/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /변경 1/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /동일 1/ })).toBeInTheDocument()
  })

  it('the status filter chips narrow the visible rows', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      pairs: [
        pair({ id: 'p-101', status: 'changed', before_frame: frame({ sheet_no: 'A-101' }) }),
        pair({ id: 'p-102', status: 'same', before_frame: frame({ sheet_no: 'A-102' }) }),
      ],
    })
    render(<SheetListScreen />)

    fireEvent.click(screen.getByRole('button', { name: /^동일/ }))

    expect(screen.queryByText('A-101')).not.toBeInTheDocument()
    expect(screen.getByText('A-102')).toBeInTheDocument()
  })

  it('search narrows by sheet number or title', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      pairs: [
        pair({ id: 'p-101', before_frame: frame({ sheet_no: 'A-101', sheet_title: '1층 평면도' }) }),
        pair({ id: 'p-102', before_frame: frame({ sheet_no: 'A-102', sheet_title: '지붕 평면도' }) }),
      ],
    })
    render(<SheetListScreen />)

    fireEvent.change(screen.getByLabelText('도면번호·제목 검색'), { target: { value: '지붕' } })

    expect(screen.queryByText('A-101')).not.toBeInTheDocument()
    expect(screen.getByText('A-102')).toBeInTheDocument()
  })

  it('도곽 열기/전체 도곽 출력 stay disabled until a comparable pair is selected / a compare has run', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      pairs: [pair({ id: 'p-101', before_frame: frame({ sheet_no: 'A-101' }) })],
    })
    render(<SheetListScreen />)

    expect(screen.getByRole('button', { name: '도곽 열기' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '전체 도곽 출력…' })).toBeDisabled()

    fireEvent.click(rowFor('A-101'))
    expect(screen.getByRole('button', { name: '도곽 열기' })).not.toBeDisabled()
  })

  it('도곽 열기 moves to the review screen with the selected pair', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      pairs: [pair({ id: 'p-101', before_frame: frame({ sheet_no: 'A-101' }) })],
    })
    render(<SheetListScreen />)

    fireEvent.click(rowFor('A-101'))
    fireEvent.click(screen.getByRole('button', { name: '도곽 열기' }))

    expect(useCompareStore.getState().screen).toBe('review')
    expect(useCompareStore.getState().selectedPairId).toBe('p-101')
  })

  it('shows the manual-pair dialog for an unpaired/added/removed row and confirms a pairing', async () => {
    useCompareStore.setState({
      compareSetId: 'cs1',
      pairsAvailable: true,
      pairs: [
        pair({
          id: 'p-removed',
          status: 'removed',
          before_frame_id: 'f-removed',
          after_frame_id: null,
          before_frame: frame({ id: 'f-removed', sheet_no: 'A-101' }),
        }),
        pair({
          id: 'p-added',
          status: 'added',
          before_frame_id: null,
          after_frame_id: 'f-added',
          after_frame: frame({ id: 'f-added', role: 'after', sheet_no: 'A-103' }),
        }),
      ],
    })
    api.createManualPair.mockResolvedValueOnce(pair({ id: 'p-manual', match_method: 'manual' }))
    api.getPairs.mockResolvedValueOnce([pair({ id: 'p-manual', match_method: 'manual' })])

    render(<SheetListScreen />)

    // Both the `removed` and `added` rows are manual-pair candidates, so
    // two "수동 짝 맞춤" buttons exist -- either opens the same dialog.
    fireEvent.click(nth(screen.getAllByRole('button', { name: '수동 짝 맞춤' }), 0))
    const dialog = screen.getByRole('dialog')
    fireEvent.click(within(dialog).getByText('A-101'))
    fireEvent.click(within(dialog).getByText('A-103'))
    fireEvent.click(within(dialog).getByRole('button', { name: '짝 맞춤 확정' }))

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    expect(api.createManualPair).toHaveBeenCalledWith('cs1', 'f-removed', 'f-added')
  })

  it('shows a manual "짝 해제" button for manually-paired rows', () => {
    useCompareStore.setState({
      pairsAvailable: true,
      pairs: [pair({ id: 'p-manual', match_method: 'manual', before_frame: frame({ sheet_no: 'A-101' }) })],
    })
    render(<SheetListScreen />)

    expect(screen.getByRole('button', { name: '짝 해제' })).toBeInTheDocument()
  })

  it('비교 실행 shows the "준비 중" toast when POST .../run 404s', async () => {
    useCompareStore.setState({
      compareSetId: 'cs1',
      pairsAvailable: true,
      pairs: [pair({ id: 'p-101', before_frame: frame({ sheet_no: 'A-101' }) })],
    })
    api.startRun.mockResolvedValueOnce(null)

    render(<SheetListScreen />)
    fireEvent.click(screen.getByRole('button', { name: '비교 실행' }))

    expect(await screen.findByText('비교 엔진이 아직 준비되지 않았습니다')).toBeInTheDocument()
  })
})
