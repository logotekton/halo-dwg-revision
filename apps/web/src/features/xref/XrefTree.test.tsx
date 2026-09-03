import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { XrefTree } from './XrefTree'
import type { XrefLink } from './api'

afterEach(() => {
  cleanup()
})

const LINKS: XrefLink[] = [
  { blockName: 'F10_GRID', declaredPath: 'F10_grid.dxf', resolvedPath: '/x/F10_grid.dxf', status: 'RESOLVED' },
  { blockName: 'PLAN', declaredPath: '..\\XR\\PLAN.dwg', resolvedPath: null, status: 'UNRESOLVED' },
]

describe('XrefTree', () => {
  it('renders the host name and one row per xref link with its status', () => {
    render(<XrefTree hostName="A-100 평면도.dwg" links={LINKS} />)

    expect(screen.getByText('A-100 평면도.dwg')).toBeInTheDocument()
    expect(screen.getByText('F10_GRID')).toBeInTheDocument()
    expect(screen.getByText('PLAN')).toBeInTheDocument()
    expect(screen.getByText('해석됨')).toBeInTheDocument()
    expect(screen.getByText('미해석')).toBeInTheDocument()
  })

  it('shows the empty-state message when there are no xrefs', () => {
    render(<XrefTree hostName="host.dxf" links={[]} />)
    expect(screen.getByText('XREF 참조 없음')).toBeInTheDocument()
  })

  it('shows the loading message while loading', () => {
    render(<XrefTree hostName="host.dxf" links={[]} loading />)
    expect(screen.getByText('XREF 정보를 불러오는 중...')).toBeInTheDocument()
  })

  it('shows an error message on error', () => {
    render(<XrefTree hostName="host.dxf" links={[]} error="network down" />)
    expect(screen.getByRole('alert')).toHaveTextContent('XREF 정보를 불러오지 못했습니다')
  })

  it('the visibility toggle is disabled for an unresolved xref', () => {
    render(<XrefTree hostName="host.dxf" links={LINKS} />)
    const [resolvedButton, unresolvedButton] = screen.getAllByText(/언로드|리로드/) as [
      HTMLElement,
      HTMLElement,
    ]
    // First link (F10_GRID) is resolved -> enabled "언로드"; second (PLAN) unresolved -> disabled.
    expect(resolvedButton).toBeEnabled()
    expect(unresolvedButton).toBeDisabled()
  })

  it('toggling a resolved xref calls onToggleVisibility and flips the label', () => {
    const onToggleVisibility = vi.fn()
    render(<XrefTree hostName="host.dxf" links={LINKS} onToggleVisibility={onToggleVisibility} />)

    const [resolvedRowButton] = screen.getAllByText('언로드') as [HTMLElement, HTMLElement]
    fireEvent.click(resolvedRowButton)

    expect(onToggleVisibility).toHaveBeenCalledWith('F10_GRID', false)
    expect(screen.getByText('리로드')).toBeInTheDocument()
  })
})
