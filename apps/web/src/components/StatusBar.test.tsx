import { cleanup, render, screen } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import '../i18n/i18n'
import type { EngineStatus } from '../api/types'
import { StatusBar } from './StatusBar'

// The shared apps/web/src/test/setup.ts doesn't set this (no auto React
// Testing Library configuration there), so act() below would otherwise warn.
;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function mockHalocad() {
  let listener: ((status: EngineStatus) => void) | null = null
  const unsubscribe = vi.fn()
  const onStatus = vi.fn((cb: (status: EngineStatus) => void) => {
    listener = cb
    return unsubscribe
  })
  Object.defineProperty(window, 'halocad', {
    configurable: true,
    value: { app: { getVersion: vi.fn(), platform: 'darwin' }, engine: { getConnection: vi.fn(), onStatus } },
  })
  return {
    emit: (status: EngineStatus) => {
      act(() => listener?.(status))
    },
    unsubscribe,
  }
}

describe('StatusBar', () => {
  beforeEach(() => {
    delete (window as { __HALO_E2E_ENABLED__?: boolean }).__HALO_E2E_ENABLED__
    delete (window as { __haloTest?: unknown }).__haloTest
  })

  afterEach(() => {
    // The shared apps/web/src/test/setup.ts does not register @testing-
    // library/react's auto-cleanup, so each test unmounts explicitly to
    // avoid leaking a still-mounted, still-listening StatusBar into the
    // next test's DOM/query results.
    cleanup()
    vi.restoreAllMocks()
  })

  it('shows "disconnected" before any status has been received', () => {
    mockHalocad()
    render(<StatusBar />)
    expect(screen.getByText('엔진: 연결 안 됨')).toBeInTheDocument()
  })

  it('shows "엔진: 연결됨 v<version>" once a ready status arrives', () => {
    const { emit } = mockHalocad()
    render(<StatusBar />)
    emit({ state: 'ready', version: '0.0.1', port: 54213 })
    expect(screen.getByText('엔진: 연결됨 v0.0.1')).toBeInTheDocument()
  })

  it('shows "재연결 중" while restarting, then "연결됨" again after a successful reconnect', () => {
    const { emit } = mockHalocad()
    render(<StatusBar />)
    emit({ state: 'restarting', attempt: 1 })
    expect(screen.getByText('엔진: 재연결 중')).toBeInTheDocument()
    emit({ state: 'ready', version: '0.0.1', port: 54213 })
    expect(screen.getByText('엔진: 연결됨 v0.0.1')).toBeInTheDocument()
  })

  it('shows the failure message after the engine gives up', () => {
    const { emit } = mockHalocad()
    render(<StatusBar />)
    emit({ state: 'failed', message: 'uv가 설치되어 있지 않습니다.' })
    expect(screen.getByText('엔진 시작 실패: uv가 설치되어 있지 않습니다.')).toBeInTheDocument()
  })

  it('unsubscribes from engine status on unmount', () => {
    const { unsubscribe } = mockHalocad()
    const { unmount } = render(<StatusBar />)
    unmount()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it('does not expose window.__haloTest when HALO_E2E is not enabled', () => {
    mockHalocad()
    render(<StatusBar />)
    expect(window.__haloTest).toBeUndefined()
  })

  it('exposes window.__haloTest.getStatus() with the current state when HALO_E2E is enabled', () => {
    window.__HALO_E2E_ENABLED__ = true
    const { emit } = mockHalocad()
    render(<StatusBar />)
    expect(window.__haloTest?.getStatus()).toBe('disconnected')
    emit({ state: 'ready', version: '0.0.1', port: 54213 })
    expect(window.__haloTest?.getStatus()).toBe('ready')
  })
})
