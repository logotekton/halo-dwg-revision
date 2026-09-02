import { describe, expect, it } from 'vitest'
import { isCloseTabShortcut, isCycleTabShortcut, isOpenShortcut } from './shortcuts'

function key(init: Partial<KeyboardEventInit> & { key: string }): KeyboardEvent {
  return new KeyboardEvent('keydown', init)
}

describe('isOpenShortcut', () => {
  it('matches Ctrl+O', () => {
    expect(isOpenShortcut(key({ key: 'o', ctrlKey: true }))).toBe(true)
  })

  it('matches Cmd+O (metaKey)', () => {
    expect(isOpenShortcut(key({ key: 'o', metaKey: true }))).toBe(true)
  })

  it('is case-insensitive on the key', () => {
    expect(isOpenShortcut(key({ key: 'O', ctrlKey: true }))).toBe(true)
  })

  it('rejects O without a modifier', () => {
    expect(isOpenShortcut(key({ key: 'o' }))).toBe(false)
  })

  it('rejects Ctrl+Shift+O', () => {
    expect(isOpenShortcut(key({ key: 'o', ctrlKey: true, shiftKey: true }))).toBe(false)
  })

  it('rejects Ctrl+W', () => {
    expect(isOpenShortcut(key({ key: 'w', ctrlKey: true }))).toBe(false)
  })
})

describe('isCloseTabShortcut', () => {
  it('matches Ctrl+W', () => {
    expect(isCloseTabShortcut(key({ key: 'w', ctrlKey: true }))).toBe(true)
  })

  it('matches Cmd+W', () => {
    expect(isCloseTabShortcut(key({ key: 'w', metaKey: true }))).toBe(true)
  })

  it('rejects W without a modifier', () => {
    expect(isCloseTabShortcut(key({ key: 'w' }))).toBe(false)
  })
})

describe('isCycleTabShortcut', () => {
  it('matches Ctrl+Tab', () => {
    expect(isCycleTabShortcut(key({ key: 'Tab', ctrlKey: true }))).toBe(true)
  })

  it('rejects Cmd+Tab (the OS app switcher)', () => {
    expect(isCycleTabShortcut(key({ key: 'Tab', metaKey: true }))).toBe(false)
  })

  it('rejects plain Tab', () => {
    expect(isCycleTabShortcut(key({ key: 'Tab' }))).toBe(false)
  })

  it('rejects Ctrl+Shift+Tab', () => {
    expect(isCycleTabShortcut(key({ key: 'Tab', ctrlKey: true, shiftKey: true }))).toBe(false)
  })
})
