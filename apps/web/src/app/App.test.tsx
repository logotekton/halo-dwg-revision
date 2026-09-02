import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n/i18n'
import { useDocumentsStore } from '../state/documents'
import { App } from './App'

// The shared apps/web/src/test/setup.ts doesn't set this (see
// apps/web/src/components/StatusBar.test.tsx for the same note).
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function mockHalocad(pickDrawings: () => Promise<string[]>): void {
  Object.defineProperty(window, 'halocad', {
    configurable: true,
    value: {
      app: { getVersion: vi.fn(), platform: 'darwin' },
      engine: { getConnection: vi.fn(), onStatus: vi.fn(() => () => undefined) },
      files: { pickDrawings },
    },
  })
}

describe('App shell', () => {
  beforeEach(() => {
    window.localStorage.clear()
    useDocumentsStore.setState({ tabs: [], activeFileId: null })
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
  })

  it('opens two tabs via the 열기 button and switches between them', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg', '/tmp/b.dxf']))
    render(<App />)

    fireEvent.click(screen.getByText('열기'))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'a.dwg' })).toBeInTheDocument()
    })
    expect(screen.getByRole('tab', { name: 'b.dxf' })).toBeInTheDocument()

    // Opening activates the last picked file.
    expect(screen.getByRole('tab', { name: 'b.dxf' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(screen.getByRole('tab', { name: 'a.dwg' }))
    expect(screen.getByRole('tab', { name: 'a.dwg' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'b.dxf' })).toHaveAttribute('aria-selected', 'false')
  })

  it('closes a tab via its close button', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg', '/tmp/b.dxf']))
    render(<App />)

    fireEvent.click(screen.getByText('열기'))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'b.dxf' })).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'b.dxf 탭 닫기' }))

    expect(screen.queryByRole('tab', { name: 'b.dxf' })).not.toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'a.dwg' })).toBeInTheDocument()
  })

  it('Ctrl+Tab cycles the active tab', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg', '/tmp/b.dxf']))
    render(<App />)

    fireEvent.click(screen.getByText('열기'))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'b.dxf' })).toHaveAttribute('aria-selected', 'true')
    })

    act(() => {
      fireEvent.keyDown(window, { key: 'Tab', ctrlKey: true })
    })

    expect(screen.getByRole('tab', { name: 'a.dwg' })).toHaveAttribute('aria-selected', 'true')
  })

  it('Ctrl+W closes the active tab', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg']))
    render(<App />)

    fireEvent.click(screen.getByText('열기'))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'a.dwg' })).toBeInTheDocument()
    })

    act(() => {
      fireEvent.keyDown(window, { key: 'w', ctrlKey: true })
    })

    expect(screen.queryByRole('tab', { name: 'a.dwg' })).not.toBeInTheDocument()
  })

  it('Ctrl+O triggers the same open flow as the 열기 button', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg']))
    render(<App />)

    act(() => {
      fireEvent.keyDown(window, { key: 'o', ctrlKey: true })
    })

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'a.dwg' })).toBeInTheDocument()
    })
  })

  it('collapses and expands the left dock', () => {
    mockHalocad(() => Promise.resolve([]))
    render(<App />)

    expect(screen.getByText('레이어')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('왼쪽 도크 접기'))
    expect(screen.queryByText('레이어')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('왼쪽 도크 펼치기'))
    expect(screen.getByText('레이어')).toBeInTheDocument()
  })

  it('collapses and expands the right dock', () => {
    mockHalocad(() => Promise.resolve([]))
    render(<App />)

    expect(screen.getByText('속성')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('오른쪽 도크 접기'))
    expect(screen.queryByText('속성')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('오른쪽 도크 펼치기'))
    expect(screen.getByText('속성')).toBeInTheDocument()
  })

  it('keeps #viewer-root empty regardless of open tabs', async () => {
    mockHalocad(() => Promise.resolve(['/tmp/a.dwg']))
    const { container } = render(<App />)

    const viewerRoot = container.querySelector('#viewer-root')
    expect(viewerRoot).not.toBeNull()
    expect(viewerRoot?.childElementCount).toBe(0)

    fireEvent.click(screen.getByText('열기'))
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'a.dwg' })).toBeInTheDocument()
    })

    expect(container.querySelector('#viewer-root')?.childElementCount).toBe(0)
  })
})
