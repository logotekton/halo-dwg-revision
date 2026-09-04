import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import '../i18n/i18n'
import { AppHeader } from './AppHeader'

describe('AppHeader', () => {
  afterEach(() => {
    cleanup()
  })

  it('renders the title and every step label', () => {
    render(<AppHeader title="Halo CAD" currentScreen="set" />)

    expect(screen.getByText('Halo CAD')).toBeInTheDocument()
    expect(screen.getByText('A 세트 지정')).toBeInTheDocument()
    expect(screen.getByText('B 도곽 목록')).toBeInTheDocument()
    expect(screen.getByText('C 검토')).toBeInTheDocument()
    expect(screen.getByText('D 출력')).toBeInTheDocument()
  })

  it('marks only the current screen with aria-current="step"', () => {
    render(<AppHeader title="Halo CAD" currentScreen="sheets" />)

    const current = screen.getByText('B 도곽 목록').closest('li')
    expect(current).toHaveAttribute('aria-current', 'step')

    const notCurrent = screen.getByText('A 세트 지정').closest('li')
    expect(notCurrent).not.toHaveAttribute('aria-current')
  })

  it('exposes the step list under an aria-label', () => {
    render(<AppHeader title="Halo CAD" currentScreen="export" />)

    expect(screen.getByRole('list', { name: '진행 단계' })).toBeInTheDocument()
  })
})
