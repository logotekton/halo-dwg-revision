import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app, BrowserWindow, protocol } from 'electron'
import { createEngineLogger, startEngineSupervisor, type EngineSupervisor } from './engine'
import type { EngineStatus } from './engine'
import { registerIpcHandlers } from './ipc'
import { getMimeType, resolveAssetPath } from './protocol'
import { APP_SCHEME, createMainWindow } from './window'

const ENGINE_STATUS_CHANNEL = 'halocad:engine:status'

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
  // Unpacked layout (dev build + `electron .`, and today's packaging):
  // apps/desktop/{package.json,out/} next to apps/web/dist.
  return join(app.getAppPath(), '..', 'web', 'dist')
}

function engineDevDir(): string {
  // apps/desktop/{package.json,out/} next to the repo-root engine/ dir
  // (docs/contracts/wave-2.md "사이드카": dev spawn cwd is `engine/`).
  return join(app.getAppPath(), '..', '..', 'engine')
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
      return new Response(new Uint8Array(data), {
        headers: { 'Content-Type': getMimeType(filePath) },
      })
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
    registerIpcHandlers(engine)
    const win = createMainWindow()
    relayEngineStatus(win, engine)

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
  engineSupervisor
    .shutdown()
    .catch((error: unknown) => {
      console.error('engine shutdown failed', error)
    })
    .finally(() => {
      app.quit()
    })
})
