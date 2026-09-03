import { readFile } from 'node:fs/promises'
import { app, BrowserWindow, protocol } from 'electron'
import { createEngineLogger, startEngineSupervisor, type EngineSupervisor } from './engine'
import { join } from 'node:path'
import type { EngineStatus } from './engine'
import { acadBridgeEntryFor, createDwgConverter, registerConvertIpc, type DwgConverter } from './convert'
import { registerE2eBridge } from './convert/e2e'
import { registerIpcHandlers } from './ipc'
import { assetHeaders, resolveAssetPath, resolveWebDistDir } from './protocol'
import { APP_SCHEME, createMainWindow } from './window'

// Invariant to how Electron was launched (`electron .` vs a file path): out/main -> apps/desktop.
const PACKAGE_ROOT = join(__dirname, '..', '..')

const ENGINE_STATUS_CHANNEL = 'halocad:engine:status'

// Test-only (HALO_E2E=1): expose V8's `gc()` and precise `performance.memory`
// in every renderer so tests/e2e/viewer.spec.ts can measure the heap after a
// forced collection instead of guessing from Chromium's 100 kB buckets
// (docs/spikes/mlightcad-api.md C.12). Both switches must be set before
// 'ready'; neither is set in a normal run.
if (process.env.HALO_E2E === '1') {
  app.commandLine.appendSwitch('js-flags', '--expose-gc')
  app.commandLine.appendSwitch('enable-precise-memory-info')
}

// Custom scheme must be registered as privileged before app 'ready' (Electron
// requirement). standard+secure+supportFetchAPI+corsEnabled per brief W1-01 /
// ADR reference so the renderer behaves like a normal https-ish origin
// (fetch, workers, relative URLs) instead of Electron's restricted default.
protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
    },
  },
])

function webDistDir(): string {
  return resolveWebDistDir({
    isPackaged: app.isPackaged,
    appPath: PACKAGE_ROOT,
    resourcesPath: process.resourcesPath,
  })
}

function engineDevDir(): string {
  // apps/desktop/{package.json,out/} next to the repo-root engine/ dir
  // (docs/contracts/wave-2.md "사이드카": dev spawn cwd is `engine/`).
  return join(PACKAGE_ROOT, '..', '..', 'engine')
}

function registerAppProtocol(): void {
  const distDir = webDistDir()

  protocol.handle(APP_SCHEME, async (request) => {
    const url = new URL(request.url)

    let filePath: string
    try {
      filePath = resolveAssetPath(distDir, url.pathname)
    } catch {
      return new Response('Forbidden', { status: 403 })
    }

    try {
      const data = await readFile(filePath)
      const headers = assetHeaders(filePath, data.byteLength)
      // `checkWorkersOnInit` probes the worker URLs with HEAD before the viewer
      // will report `workersReady` (spike §A, requirement 6). A HEAD that is
      // not answered leaves the viewer permanently "not ready", so it is served
      // with the same headers and an empty body.
      if (request.method === 'HEAD') {
        return new Response(null, { headers })
      }
      return new Response(new Uint8Array(data), { headers })
    } catch {
      return new Response('Not Found', { status: 404 })
    }
  })
}

/** Sends the engine's current status to a window once its page has loaded, then keeps it live. */
function relayEngineStatus(win: BrowserWindow, engine: EngineSupervisor): void {
  const send = (status: EngineStatus): void => {
    if (!win.isDestroyed()) win.webContents.send(ENGINE_STATUS_CHANNEL, status)
  }
  // webContents.send() before the renderer's ipcRenderer.on() listener is
  // attached can be lost, so push the current snapshot once the page has
  // actually finished loading, then rely on onStatus() for anything after.
  win.webContents.once('did-finish-load', () => {
    send(engine.getStatus())
  })
  const unsubscribe = engine.onStatus(send)
  win.once('closed', unsubscribe)
}

let engineSupervisor: EngineSupervisor | null = null
let dwgConverter: DwgConverter | null = null
let quitting = false

app
  .whenReady()
  .then(() => {
    const logger = createEngineLogger(join(app.getPath('userData'), 'logs'))
    const engine = startEngineSupervisor({
      isPackaged: app.isPackaged,
      engineDir: engineDevDir(),
      resourcesPath: process.resourcesPath,
      dataDir: join(app.getPath('userData'), 'engine'),
      logger,
    })
    engineSupervisor = engine

    registerAppProtocol()
    // DWG -> DXF runs in a hidden BrowserWindow because the mlightcad DWG
    // parser needs a Web Worker (ADR-0002 개정 2026-09-02 §2). It is created
    // lazily on the first conversion and torn down after five idle minutes.
    const converter = createDwgConverter({
      preloadPath: join(__dirname, '../preload/convert.js'),
      acadBridgeEntry: acadBridgeEntryFor(PACKAGE_ROOT),
    })
    dwgConverter = converter
    registerIpcHandlers(engine)
    // Registered separately from `registerIpcHandlers` so this task does not
    // touch `ipc.ts`, which W3-01 extends with `halocad:files:*` in parallel.
    registerConvertIpc(converter)
    // No-op unless HALO_E2E=1 (docs/dev/e2e.md).
    registerE2eBridge(converter)
    const win = createMainWindow()
    relayEngineStatus(win, engine)
    // The hidden converter window would otherwise keep 'window-all-closed'
    // from firing on Windows/Linux; it is recreated on the next conversion.
    win.once('closed', () => {
      converter.dispose()
    })

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        const reactivatedWin = createMainWindow()
        relayEngineStatus(reactivatedWin, engine)
      }
    })
  })
  .catch((error: unknown) => {
    // Startup failure: no renderer window exists yet to show this in.
    console.error('failed to start Halo CAD', error)
    app.exit(1)
  })

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// Engine shutdown (docs/contracts/wave-2.md "사이드카": POST /shutdown → 5s
// grace → SIGTERM/taskkill) must finish before Electron actually exits, so
// the first before-quit is deferred with preventDefault() and app.quit() is
// re-issued once cleanup settles.
app.on('before-quit', (event) => {
  if (quitting || !engineSupervisor) return
  quitting = true
  event.preventDefault()
  dwgConverter?.dispose()
  dwgConverter = null
  engineSupervisor
    .shutdown()
    .catch((error: unknown) => {
      console.error('engine shutdown failed', error)
    })
    .finally(() => {
      app.quit()
    })
})
