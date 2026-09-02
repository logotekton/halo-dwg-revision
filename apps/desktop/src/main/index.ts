import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app, BrowserWindow, protocol } from 'electron'
import { registerIpcHandlers } from './ipc'
import { getMimeType, resolveAssetPath } from './protocol'
import { APP_SCHEME, createMainWindow } from './window'

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

app
  .whenReady()
  .then(() => {
    registerAppProtocol()
    registerIpcHandlers()
    createMainWindow()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createMainWindow()
      }
    })
  })
  .catch((error: unknown) => {
    // Startup failure: no renderer window exists yet to show this in.
    console.error('failed to start DMCAD', error)
    app.exit(1)
  })

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
