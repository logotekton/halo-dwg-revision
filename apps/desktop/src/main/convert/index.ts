import { randomUUID } from 'node:crypto'
import { readFile, writeFile } from 'node:fs/promises'
import { basename, join } from 'node:path'
import { BrowserWindow, ipcMain, type IpcMainEvent } from 'electron'
import { VIEWER_ASSETS_BASE } from '../protocol'
import { APP_SCHEME } from '../window'
import { runAcadTsFallback } from './fallback'
import {
  CONVERT_INVOKE_CHANNEL,
  CONVERT_READY_CHANNEL,
  CONVERT_REQUEST_CHANNEL,
  CONVERT_RESULT_CHANNEL,
  VIEWER_ASSETS_BASE_CHANNEL,
  type ConvertReply,
  type ConvertResult,
} from './protocol'

/**
 * DWG → DXF conversion in a **hidden BrowserWindow**.
 *
 * ADR-0002 (개정 2026-09-02 §2): mlightcad's DWG converter forces
 * `useWorker: true` and Node has no `Worker` global, so the conversion cannot
 * run in a utilityProcess. A hidden renderer is the smallest context that has
 * Web Workers, `WebAssembly.instantiateStreaming` and our custom scheme.
 *
 * Layout:
 *
 * ```
 *   main ──ipc(request: DWG bytes)──▶ hidden BrowserWindow (halocad://app/convert.html)
 *                                     │ registerLibreDwgConverter (GPL, dwg-io-gpl)
 *                                     │ openDwg → exportDxf → postProcessDxfOut
 *   main ◀─ipc(reply: DXF text)───────┘
 *   main writes the file, returns { dxf_path, entity_count, converter, warnings }
 * ```
 *
 * The window is reused across requests and destroyed after
 * {@link IDLE_TIMEOUT_MS} of inactivity (brief W3-02, Constraints). One request
 * runs at a time: two 200k-entity parses in one renderer would share a single
 * ~4 GB heap (`docs/spikes/large-file.md` §3.4).
 */

/** Destroy the hidden window after five idle minutes. */
const IDLE_TIMEOUT_MS = 5 * 60 * 1000
/** A 250k-entity DWG parsed in ~2 s; the ceiling is for pathological files. */
const CONVERT_TIMEOUT_MS = 10 * 60 * 1000
/** The page must announce itself within this window or the request fails. */
const READY_TIMEOUT_MS = 60 * 1000

export interface DwgConverterOptions {
  /** Preload script for the hidden window (`out/preload/convert.js`). */
  preloadPath: string
  /** Where `runAcadTsFallback` finds `packages/acad-bridge/bin/acad-bridge.mjs`. */
  acadBridgeEntry: string | null
}

export interface ConvertJob {
  /** Absolute path of the source DWG. Never written to (CLAUDE.md rule 1). */
  dwgPath: string
  /** Absolute path the converted DXF is written to; inside the engine's cache. */
  outPath: string
}

export interface DwgConverter {
  convert(job: ConvertJob): Promise<ConvertResult>
  dispose(): void
}

interface Pending {
  resolve: (reply: ConvertReply) => void
  reject: (error: Error) => void
  timer: NodeJS.Timeout
}

export function createDwgConverter(options: DwgConverterOptions): DwgConverter {
  let window: BrowserWindow | null = null
  let ready: Promise<void> | null = null
  let idleTimer: NodeJS.Timeout | null = null
  let queue: Promise<unknown> = Promise.resolve()
  const pending = new Map<string, Pending>()

  const onResult = (_event: IpcMainEvent, reply: ConvertReply): void => {
    const entry = pending.get(reply.requestId)
    if (!entry) return
    pending.delete(reply.requestId)
    clearTimeout(entry.timer)
    entry.resolve(reply)
  }
  ipcMain.on(CONVERT_RESULT_CHANNEL, onResult)

  function touchIdleTimer(): void {
    if (idleTimer) clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      destroyWindow()
    }, IDLE_TIMEOUT_MS)
    idleTimer.unref()
  }

  function destroyWindow(): void {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
    ready = null
    const current = window
    window = null
    if (current && !current.isDestroyed()) current.destroy()
  }

  function ensureWindow(): Promise<void> {
    if (window && !window.isDestroyed() && ready) return ready
    // `show: false` + `offscreen: false`: a normal renderer that is never
    // mapped. Offscreen rendering would disable the compositor, and the
    // libredwg worker needs a plain renderer, not a GPU surface.
    const created = new BrowserWindow({
      show: false,
      width: 640,
      height: 480,
      webPreferences: {
        preload: options.preloadPath,
        contextIsolation: true,
        sandbox: true,
        nodeIntegration: false,
        webSecurity: true,
        // The wasm heap of libredwg-web can grow past the default budget on a
        // background renderer; keep it alive while a conversion is in flight.
        backgroundThrottling: false,
      },
    })
    window = created
    ready = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error('convert window did not become ready in time'))
      }, READY_TIMEOUT_MS)
      const onReady = (event: IpcMainEvent): void => {
        if (event.sender !== created.webContents) return
        clearTimeout(timer)
        ipcMain.off(CONVERT_READY_CHANNEL, onReady)
        resolve()
      }
      ipcMain.on(CONVERT_READY_CHANNEL, onReady)
      created.webContents.once('render-process-gone', (_event, details) => {
        clearTimeout(timer)
        reject(new Error(`convert window crashed: ${details.reason}`))
      })
    })
    // Same origin as the main window so the worker and wasm URLs resolve
    // exactly as they do in the viewer (spike §A, Electron requirement 1).
    void created.loadURL(`${APP_SCHEME}://app/convert.html`)
    return ready
  }

  async function runInWindow(job: ConvertJob, bytes: Buffer): Promise<ConvertResult> {
    await ensureWindow()
    const current = window
    if (!current || current.isDestroyed()) throw new Error('convert window is gone')
    const requestId = randomUUID()
    const reply = await new Promise<ConvertReply>((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(requestId)
        reject(new Error('conversion timed out'))
      }, CONVERT_TIMEOUT_MS)
      timer.unref()
      pending.set(requestId, { resolve, reject, timer })
      current.webContents.send(CONVERT_REQUEST_CHANNEL, {
        requestId,
        bytes: new Uint8Array(bytes),
        name: basename(job.dwgPath),
      })
    })
    if (!reply.ok || reply.dxf === undefined) {
      throw new Error(reply.error ?? 'conversion failed in the converter window')
    }
    await writeFile(job.outPath, reply.dxf, 'utf8')
    return {
      dxf_path: job.outPath,
      entity_count: reply.entityCount ?? 0,
      converter: 'mlightcad-dxfout',
      warnings: reply.warnings,
    }
  }

  async function convertOnce(job: ConvertJob): Promise<ConvertResult> {
    touchIdleTimer()
    // The original is opened read-only and never written to (CLAUDE.md rule 1);
    // the result goes to `job.outPath`, which the engine owns.
    const bytes = await readFile(job.dwgPath)
    try {
      return await runInWindow(job, bytes)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      // A crashed renderer leaves the window unusable; drop it so the next
      // request starts clean.
      destroyWindow()
      const fallback = await runAcadTsFallback({
        entry: options.acadBridgeEntry,
        dwgPath: job.dwgPath,
        outPath: job.outPath,
      })
      return {
        ...fallback,
        warnings: [
          // ADR-0002 개정 §4 / brief W3-02: acad-ts output is not repaired here.
          // It is handed to the engine as is and only announced to the user if
          // the engine's crosscheck rejects it (W3-08 owns the writer defects).
          `mlightcad-dxfout failed: ${message}`,
          ...fallback.warnings,
        ],
      }
    } finally {
      touchIdleTimer()
    }
  }

  return {
    convert(job: ConvertJob): Promise<ConvertResult> {
      // Serialised: one big parse at a time per renderer heap.
      const next = queue.then(
        () => convertOnce(job),
        () => convertOnce(job)
      )
      queue = next.catch(() => undefined)
      return next
    },
    dispose(): void {
      ipcMain.off(CONVERT_RESULT_CHANNEL, onResult)
      for (const entry of pending.values()) {
        clearTimeout(entry.timer)
        entry.reject(new Error('converter disposed'))
      }
      pending.clear()
      destroyWindow()
    },
  }
}

/** Default location of the acad-ts fallback CLI in a dev checkout. */
export function acadBridgeEntryFor(packageRoot: string): string {
  return join(packageRoot, '..', '..', 'packages', 'acad-bridge', 'bin', 'acad-bridge.mjs')
}

/**
 * Registers the two channels this task owns
 * (`docs/contracts/wave-3.md` "IPC 채널").
 *
 * Kept out of `src/main/ipc.ts` so W3-01 can add `halocad:files:*` there
 * without a merge conflict.
 *
 * `halocad:convert:dwg-to-dxf` is described as "main 내부용" in the contract:
 * the engine asks for a conversion over its WebSocket and main answers. It is
 * exposed as an `ipcMain.handle` anyway so the renderer's import flow (and the
 * e2e harness) can drive the same code path without a running engine.
 */
export function registerConvertIpc(converter: DwgConverter): void {
  ipcMain.handle(
    CONVERT_INVOKE_CHANNEL,
    async (_event, job: ConvertJob): Promise<ConvertResult> => converter.convert(job),
  )
  ipcMain.handle(VIEWER_ASSETS_BASE_CHANNEL, () => VIEWER_ASSETS_BASE)
}
