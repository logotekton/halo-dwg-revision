import { writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { app, BrowserWindow } from 'electron'
import strings from './strings.ko.json'

export const APP_SCHEME = 'halocad'

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

/**
 * Test-only smoke hook (opt-in via HALO_E2E_SMOKE=1): once the renderer has
 * finished loading, prints the actual BrowserWindow title, optionally
 * captures a PNG screenshot via webContents.capturePage(), then quits.
 * Used to verify `pnpm dev` from an automated/non-interactive shell.
 */
function attachE2eSmokeHook(win: BrowserWindow): void {
  if (process.env.HALO_E2E_SMOKE !== '1') return

  let finished = false
  const finish = async (): Promise<void> => {
    if (finished) return
    finished = true

    // Deliberate stdout contract for the e2e smoke check (docs/dev/setup.md).
    console.log(`E2E_WINDOW_TITLE:${win.getTitle()}`)

    const screenshotPath = process.env.HALO_E2E_SCREENSHOT
    if (screenshotPath) {
      // Let the compositor actually paint a frame before capturing: right
      // after did-finish-load the window may still be hidden (ready-to-show)
      // or mid-layout, which captures blank.
      await delay(500)
      const image = await win.webContents.capturePage()
      await writeFile(screenshotPath, image.toPNG())
      console.log(`E2E_SCREENSHOT_WRITTEN:${screenshotPath}`)
    }

    setTimeout(() => {
      app.quit()
    }, 200)
  }

  win.webContents.once('did-finish-load', () => {
    void finish()
  })

  // Safety net in case did-finish-load never fires (e.g. dev server unreachable).
  setTimeout(() => {
    void finish()
  }, 15000)
}

export function createMainWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    title: strings.window.title,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  })

  // The loaded page's <title> would otherwise override the window title;
  // keep it pinned to the Korean product name regardless of page content.
  win.on('page-title-updated', (event) => {
    event.preventDefault()
    win.setTitle(strings.window.title)
  })

  win.once('ready-to-show', () => {
    win.show()
  })

  // HALO_WEB_DEV_SERVER_URL is set only by scripts/dev.mjs. Its absence
  // means "run against the built apps/web/dist via the halocad:// protocol"
  // (used by `pnpm build && pnpm --filter @halo-cad/desktop start`).
  const devServerUrl = process.env.HALO_WEB_DEV_SERVER_URL ?? undefined
  if (devServerUrl) {
    void win.loadURL(devServerUrl)
  } else {
    void win.loadURL(`${APP_SCHEME}://app/index.html`)
  }

  attachE2eSmokeHook(win)

  return win
}
