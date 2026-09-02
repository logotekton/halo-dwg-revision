import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import '../../i18n/i18n'
import { OpenFilesButton } from './OpenFilesButton'

afterEach(() => {
  cleanup()
})

describe('OpenFilesButton', () => {
  it('calls onOpen when the "열기" button is clicked', () => {
    const onOpen = vi.fn()
    render(<OpenFilesButton recent={[]} onOpen={onOpen} onOpenRecent={vi.fn()} />)

    fireEvent.click(screen.getByText('열기'))
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('shows a disabled empty-state entry when there are no recent files', () => {
    render(<OpenFilesButton recent={[]} onOpen={vi.fn()} onOpenRecent={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('최근 파일'))
    expect(screen.getByText('최근 파일 없음')).toBeInTheDocument()
  })

  it('lists recent files and calls onOpenRecent with the clicked path', () => {
    const onOpenRecent = vi.fn()
    render(<OpenFilesButton recent={['/a.dwg', '/b.dxf']} onOpen={vi.fn()} onOpenRecent={onOpenRecent} />)

    fireEvent.click(screen.getByLabelText('최근 파일'))
    fireEvent.click(screen.getByText('/b.dxf'))

    expect(onOpenRecent).toHaveBeenCalledWith('/b.dxf')
  })

  it('closes the recent-files dropdown after picking an entry', () => {
    render(<OpenFilesButton recent={['/a.dwg']} onOpen={vi.fn()} onOpenRecent={vi.fn()} />)

    fireEvent.click(screen.getByLabelText('최근 파일'))
    fireEvent.click(screen.getByText('/a.dwg'))

    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })
})
