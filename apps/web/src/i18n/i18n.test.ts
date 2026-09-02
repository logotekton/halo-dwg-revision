import { describe, expect, it } from 'vitest'
import ko from './ko.json'

interface NestedRecord {
  [key: string]: string | NestedRecord
}

function collectKeys(value: NestedRecord, prefix = ''): string[] {
  return Object.entries(value).flatMap(([key, child]) => {
    const path = prefix ? `${prefix}.${key}` : key
    return typeof child === 'string' ? [path] : collectKeys(child, path)
  })
}

// Every key the app shell (AppHeader/StatusBar/canvas placeholder) reads via
// t(...). Keep this list in sync with call sites so a removed/renamed key
// fails this test instead of silently falling back to the raw key at runtime.
const REQUIRED_KEYS = ['app.title', 'canvas.areaLabel', 'canvas.placeholder', 'status.engineDisconnected']

describe('ko i18n resource', () => {
  const keys = collectKeys(ko)

  it('loads as a nested object', () => {
    expect(ko).toBeTypeOf('object')
    expect(keys.length).toBeGreaterThan(0)
  })

  it('defines every key the app shell requires', () => {
    for (const required of REQUIRED_KEYS) {
      expect(keys).toContain(required)
    }
  })

  it('has no empty leaf values', () => {
    for (const key of keys) {
      const value = key.split('.').reduce<NestedRecord | string>((node, segment) => {
        if (typeof node === 'string') return node
        return node[segment] ?? ''
      }, ko)
      expect(typeof value).toBe('string')
      expect((value as string).trim().length).toBeGreaterThan(0)
    }
  })

  it('detects a key that is missing from the resource (regression guard)', () => {
    expect(keys).not.toContain('nonexistent.key.for.regression.test')
  })
})
