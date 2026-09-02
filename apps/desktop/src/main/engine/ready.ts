import { createInterface } from 'node:readline'
import type { Readable } from 'node:stream'

/**
 * The sidecar's READY handshake (`docs/contracts/wave-2.md` "사이드카"): the
 * first stdout line the engine prints, once it has bound its port.
 */
export interface EngineReadyInfo {
  port: number
  pid: number
  version: string
}

/**
 * Parses one stdout line as the READY handshake. Returns `null` for anything
 * that is not a well-formed READY line — blank noise, a broken/partial JSON
 * fragment, an unrelated JSON object, or one missing/mistyping a required
 * field — so the caller can treat those lines as ordinary log noise instead
 * of crashing on them (constraint: "READY 파서는 ... 첫 JSON 줄만 해석").
 */
export function parseReadyLine(line: string): EngineReadyInfo | null {
  const trimmed = line.trim()
  if (trimmed.length === 0) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(trimmed)
  } catch {
    return null
  }

  if (typeof parsed !== 'object' || parsed === null) return null
  const obj = parsed as Record<string, unknown>

  if (obj.event !== 'ready') return null
  if (typeof obj.port !== 'number' || !Number.isInteger(obj.port) || obj.port <= 0) return null
  if (typeof obj.pid !== 'number' || !Number.isInteger(obj.pid) || obj.pid <= 0) return null
  if (typeof obj.version !== 'string' || obj.version.length === 0) return null

  return { port: obj.port, pid: obj.pid, version: obj.version }
}

export class ReadyTimeoutError extends Error {}
export class ReadyStreamClosedError extends Error {}

export interface WaitForReadyOptions {
  /** Milliseconds to wait for a valid READY line before giving up. */
  timeoutMs: number
  /** Called for every stdout line that is not the READY line (log noise). */
  onNoise: (line: string) => void
}

/**
 * Reads `stdout` line by line until the first valid READY line appears,
 * forwarding every other line to `onNoise`. Rejects with `ReadyTimeoutError`
 * if nothing valid arrives within `timeoutMs`, or `ReadyStreamClosedError` if
 * the stream ends first.
 */
export function waitForReady(stdout: Readable, options: WaitForReadyOptions): Promise<EngineReadyInfo> {
  return new Promise((resolve, reject) => {
    const rl = createInterface({ input: stdout })
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      rl.close()
      reject(new ReadyTimeoutError(`engine did not print a READY line within ${String(options.timeoutMs)}ms`))
    }, options.timeoutMs)

    rl.on('line', (line) => {
      if (settled) return
      const info = parseReadyLine(line)
      if (info) {
        settled = true
        clearTimeout(timer)
        rl.close()
        resolve(info)
        return
      }
      options.onNoise(line)
    })

    rl.on('close', () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      reject(new ReadyStreamClosedError('engine stdout closed before printing a READY line'))
    })
  })
}
