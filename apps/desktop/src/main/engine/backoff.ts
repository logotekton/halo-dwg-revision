/**
 * Restart backoff schedule (`docs/contracts/wave-2.md`: "재시작 백오프 1s, 3s,
 * 9s"). After `RESTART_BACKOFF_MS.length` consecutive crash-restart failures
 * the supervisor gives up and moves to `failed`.
 */
export const RESTART_BACKOFF_MS: readonly number[] = [1000, 3000, 9000]

export const MAX_RESTART_ATTEMPTS = RESTART_BACKOFF_MS.length

/**
 * `attempt` is 1-based: the Nth restart attempt about to be made after a
 * crash. Returns the delay to wait before making it, or `null` once attempts
 * are exhausted (the caller should transition to `failed` instead).
 */
export function backoffDelayMs(attempt: number): number | null {
  if (!Number.isInteger(attempt) || attempt < 1) {
    throw new RangeError(`attempt must be a positive integer, got ${String(attempt)}`)
  }
  return RESTART_BACKOFF_MS[attempt - 1] ?? null
}
