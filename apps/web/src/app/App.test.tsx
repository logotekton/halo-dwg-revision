import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n/i18n'
import { useCompareStore } from '../state/compare'
import { App } from './App'

// The shared apps/web/src/test/setup.ts doesn't set this (see
// apps/web/src/components/StatusBar.test.tsx for the same note).
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

/**
 * The old shell tests (open files, tabs, dock collapse) went away with the
 * shell they exercised (brief R1-05 Goal 1: "관련 테스트... 새 셸에 맞춘다")
 * -- `features/files`/`features/xref`/dock component tests are untouched
 * and still pass on their own, they are just no longer reachable from
 * `App`. This file now only covers the shell itself: header + step
 * indicator + status bar + "screen A renders by default".
 */
function mockHalocad(): void {
  Object.defineProperty(window, 'halocad', {
    configurable: true,
    value: {
      app: { getVersion: vi.fn(), platform: 'darwin' },
      engine: {
        getConnection: vi.fn().mockResolvedValue({ baseUrl: 'http://127.0.0.1:0', token: 't' }),
        onStatus: vi.fn(() => () => undefined),
      },
      files: { pickDrawings: vi.fn().mockResolvedValue([]) },
      dialog: { pickFolder: vi.fn().mockResolvedValue(null) },
      clipboard: { writeText: vi.fn() },
      shell: { openPath: vi.fn() },
    },
  })
}

describe('App shell', () => {
  beforeEach(() => {
    mockHalocad()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({ available: false, installed: false, version: null, prog_id: null, reason: 'not_windows' }),
        text: () => Promise.resolve(''),
      }),
    )
    useCompareStore.setState(useCompareStore.getInitialState(), true)
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders the title, all four step labels, and the status bar', () => {
    render(<App />)

    expect(screen.getByText('Halo CAD')).toBeInTheDocument()
    expect(document.querySelector('header')).not.toBeNull()
    expect(screen.getByRole('list', { name: '진행 단계' })).toBeInTheDocument()
    expect(document.querySelector('footer')).not.toBeNull()
  })

  it('renders screen A (세트 지정) by default', () => {
    render(<App />)

    expect(screen.getByTestId('set-screen')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '인입 시작' })).toBeInTheDocument()
  })

  it('the header step indicator tracks the compare store screen', async () => {
    render(<App />)

    act(() => {
      useCompareStore.getState().goto('sheets')
    })

    await waitFor(() => {
      expect(screen.getByText('B 도곽 목록').closest('li')).toHaveAttribute('aria-current', 'step')
    })
    expect(screen.getByTestId('sheets-screen')).toBeInTheDocument()
  })
})
