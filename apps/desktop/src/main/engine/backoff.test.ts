import { describe, expect, it } from 'vitest'
import { backoffDelayMs, MAX_RESTART_ATTEMPTS, RESTART_BACKOFF_MS } from './backoff'

describe('backoffDelayMs', () => {
  it('returns the 1s/3s/9s sequence for attempts 1-3', () => {
    expect(backoffDelayMs(1)).toBe(1000)
    expect(backoffDelayMs(2)).toBe(3000)
    expect(backoffDelayMs(3)).toBe(9000)
  })

  it('returns null once attempts are exhausted (attempt 4+)', () => {
    expect(backoffDelayMs(4)).toBeNull()
    expect(backoffDelayMs(5)).toBeNull()
  })

  it('matches MAX_RESTART_ATTEMPTS / RESTART_BACKOFF_MS.length (3)', () => {
    expect(MAX_RESTART_ATTEMPTS).toBe(3)
    expect(RESTART_BACKOFF_MS).toEqual([1000, 3000, 9000])
  })

  it('throws for a non-positive or non-integer attempt', () => {
    expect(() => backoffDelayMs(0)).toThrow(RangeError)
    expect(() => backoffDelayMs(-1)).toThrow(RangeError)
    expect(() => backoffDelayMs(1.5)).toThrow(RangeError)
  })
})
