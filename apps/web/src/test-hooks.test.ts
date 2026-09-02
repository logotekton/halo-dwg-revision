import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { registerHaloTestHook } from './test-hooks'

describe('registerHaloTestHook', () => {
  beforeEach(() => {
    delete (window as { __HALO_E2E_ENABLED__?: boolean }).__HALO_E2E_ENABLED__
    delete (window as { __haloTest?: unknown }).__haloTest
  })

  afterEach(() => {
    delete (window as { __HALO_E2E_ENABLED__?: boolean }).__HALO_E2E_ENABLED__
    delete (window as { __haloTest?: unknown }).__haloTest
  })

  it('does not expose window.__haloTest when HALO_E2E is not enabled', () => {
    registerHaloTestHook('getStatus', () => 'ready')
    expect(window.__haloTest).toBeUndefined()
  })

  it('exposes the registered getter once HALO_E2E is enabled', () => {
    window.__HALO_E2E_ENABLED__ = true
    registerHaloTestHook('getStatus', () => 'ready')
    expect(window.__haloTest?.getStatus()).toBe('ready')
  })

  it('merges getters registered under different keys instead of overwriting', () => {
    window.__HALO_E2E_ENABLED__ = true
    registerHaloTestHook('getStatus', () => 'ready')
    registerHaloTestHook('getDocuments', () => [{ fileId: 'a', name: 'a.dwg', layers: 2 }])

    expect(window.__haloTest?.getStatus()).toBe('ready')
    expect(window.__haloTest?.getDocuments()).toEqual([{ fileId: 'a', name: 'a.dwg', layers: 2 }])
  })

  it('re-registering the same key replaces only that getter', () => {
    window.__HALO_E2E_ENABLED__ = true
    registerHaloTestHook('getDocuments', () => [])
    registerHaloTestHook('getStatus', () => 'starting')
    registerHaloTestHook('getStatus', () => 'ready')

    expect(window.__haloTest?.getStatus()).toBe('ready')
    expect(window.__haloTest?.getDocuments()).toEqual([])
  })
})
