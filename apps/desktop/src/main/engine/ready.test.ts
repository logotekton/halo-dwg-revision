import { PassThrough, Readable } from 'node:stream'
import { describe, expect, it } from 'vitest'
import { parseReadyLine, ReadyStreamClosedError, ReadyTimeoutError, waitForReady } from './ready'

describe('parseReadyLine', () => {
  it('parses a well-formed READY line', () => {
    const line = '{"event":"ready","port":54213,"pid":41213,"version":"0.0.1"}'
    expect(parseReadyLine(line)).toEqual({ port: 54213, pid: 41213, version: '0.0.1' })
  })

  it('tolerates trailing whitespace/newline', () => {
    const line = '{"event":"ready","port":1,"pid":2,"version":"1.2.3"}  \n'
    expect(parseReadyLine(line)).toEqual({ port: 1, pid: 2, version: '1.2.3' })
  })

  it('returns null for a blank line', () => {
    expect(parseReadyLine('')).toBeNull()
    expect(parseReadyLine('   ')).toBeNull()
  })

  it('returns null for broken JSON', () => {
    expect(parseReadyLine('{"event":"ready","port":1,')).toBeNull()
  })

  it('returns null for noise lines printed before READY', () => {
    expect(parseReadyLine('Starting halo_engine...')).toBeNull()
    expect(parseReadyLine('INFO:     Uvicorn running')).toBeNull()
  })

  it('returns null for a JSON line that is not the ready event', () => {
    expect(parseReadyLine('{"event":"log","message":"hello"}')).toBeNull()
  })

  it('returns null when a required field is missing or mistyped', () => {
    expect(parseReadyLine('{"event":"ready","pid":2,"version":"1.0.0"}')).toBeNull()
    expect(parseReadyLine('{"event":"ready","port":"54213","pid":2,"version":"1.0.0"}')).toBeNull()
    expect(parseReadyLine('{"event":"ready","port":0,"pid":2,"version":"1.0.0"}')).toBeNull()
    expect(parseReadyLine('{"event":"ready","port":1,"pid":2,"version":""}')).toBeNull()
  })

  it('returns null for a bare JSON array or primitive', () => {
    expect(parseReadyLine('[1,2,3]')).toBeNull()
    expect(parseReadyLine('42')).toBeNull()
    expect(parseReadyLine('null')).toBeNull()
  })
})

describe('waitForReady', () => {
  it('resolves with the first valid READY line and forwards earlier noise', async () => {
    const noise: string[] = []
    const stdout = Readable.from(
      ['Starting halo_engine...\n', 'INFO:     Uvicorn running\n', '{"event":"ready","port":9,"pid":1,"version":"0.0.1"}\n'],
      { objectMode: false },
    )

    const info = await waitForReady(stdout, { timeoutMs: 1000, onNoise: (line) => noise.push(line) })

    expect(info).toEqual({ port: 9, pid: 1, version: '0.0.1' })
    expect(noise).toEqual(['Starting halo_engine...', 'INFO:     Uvicorn running'])
  })

  it('ignores lines after the READY line (does not forward them as noise)', async () => {
    const noise: string[] = []
    const stdout = Readable.from(['{"event":"ready","port":9,"pid":1,"version":"0.0.1"}\n', 'later log line\n'])

    await waitForReady(stdout, { timeoutMs: 1000, onNoise: (line) => noise.push(line) })
    // give the stream a tick to (not) emit further lines
    await new Promise((resolve) => setTimeout(resolve, 10))

    expect(noise).toEqual([])
  })

  it('rejects with ReadyTimeoutError when nothing valid arrives in time', async () => {
    // A stream that stays open (no EOF) so the timeout — not stream-close —
    // is what triggers the rejection.
    const stdout = new PassThrough()
    stdout.write('just some noise\n')
    const promise = waitForReady(stdout, { timeoutMs: 20, onNoise: () => undefined })
    await expect(promise).rejects.toBeInstanceOf(ReadyTimeoutError)
    stdout.destroy()
  })

  it('rejects with ReadyStreamClosedError when stdout ends before READY', async () => {
    const stdout = Readable.from(['noise only, then EOF\n'])
    await expect(waitForReady(stdout, { timeoutMs: 5000, onNoise: () => undefined })).rejects.toBeInstanceOf(
      ReadyStreamClosedError,
    )
  })
})
