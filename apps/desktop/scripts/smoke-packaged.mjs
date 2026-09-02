#!/usr/bin/env node
// Smoke-tests the *packaged* Halo CAD.app (built by `tools/package.sh` /
// `pnpm --filter @halo-cad/desktop build:app`) by launching the real
// installed binary with the main-process E2E smoke hook (HALO_E2E_SMOKE=1,
// see `apps/desktop/src/main/window.ts` and docs/dev/setup.md's dev-mode
// equivalent) and checking its stdout -- same hook, packaged binary instead
// of `pnpm dev`.
//
// Usage: node apps/desktop/scripts/smoke-packaged.mjs
// Exit 0 + a "PASS" line on success, non-zero otherwise. Times out after
// 120s per docs/briefs/W2-08.md.

import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
// apps/desktop/scripts -> apps/desktop -> apps -> <repo root>
const REPO_ROOT = join(__dirname, '..', '..', '..')
const APP_PATH = join(REPO_ROOT, 'dist', 'mac-arm64', 'Halo CAD.app')
const APP_BINARY = join(APP_PATH, 'Contents', 'MacOS', 'Halo CAD')
const TIMEOUT_MS = 120_000

// Contract channel name (docs/contracts/wave-2.md "IPC 채널") that W2-01's
// preload bridge exposes once merged. Used only to decide whether to *also*
// point at the status-bar screenshot for a manual look -- its absence is not
// a failure (see docs/briefs/W2-08.md: "W2-01이 병합돼 있으면 ... 확인").
const ENGINE_IPC_CHANNEL = 'halocad:engine:get-connection'

function fail(message) {
  console.error(`FAIL: ${message}`)
  process.exit(1)
}

if (!existsSync(APP_BINARY)) {
  fail(
    `packaged app binary not found at ${APP_BINARY}\n` +
      `Run tools/package.sh (or "pnpm --filter @halo-cad/desktop build:app") first.`,
  )
}

const scratchDir = mkdtempSync(join(tmpdir(), 'halocad-smoke-'))
const screenshotPath = join(scratchDir, 'packaged-smoke.png')

console.log(`launching packaged app: ${APP_BINARY}`)

const child = spawn(APP_BINARY, [], {
  env: {
    ...process.env,
    HALO_E2E_SMOKE: '1',
    HALO_E2E_SCREENSHOT: screenshotPath,
  },
  stdio: ['ignore', 'pipe', 'pipe'],
})

let stdout = ''
let stderr = ''
child.stdout.on('data', (chunk) => {
  stdout += chunk.toString()
})
child.stderr.on('data', (chunk) => {
  stderr += chunk.toString()
})

const timer = setTimeout(() => {
  child.kill('SIGKILL')
  fail(`packaged app did not exit within ${TIMEOUT_MS / 1000}s`)
}, TIMEOUT_MS)

child.on('error', (err) => {
  clearTimeout(timer)
  fail(`failed to launch packaged app: ${String(err)}`)
})

child.on('exit', (code) => {
  clearTimeout(timer)

  const titleMatch = /^E2E_WINDOW_TITLE:(.*)$/m.exec(stdout)
  if (!titleMatch) {
    console.error('--- stdout ---')
    console.error(stdout)
    console.error('--- stderr ---')
    console.error(stderr)
    fail('no E2E_WINDOW_TITLE line in stdout')
  }
  const title = titleMatch[1].trim()
  console.log(`E2E_WINDOW_TITLE:${title}`)
  if (title !== 'Halo CAD') {
    fail(`unexpected window title: ${JSON.stringify(title)} (expected "Halo CAD")`)
  }

  if (existsSync(screenshotPath)) {
    console.log(`screenshot written: ${screenshotPath}`)
  } else {
    console.warn('warning: no screenshot was written (HALO_E2E_SCREENSHOT path missing)')
  }

  let preloadHasEngineApi = false
  try {
    const preloadSrc = readFileSync(join(REPO_ROOT, 'apps/desktop/src/preload/index.ts'), 'utf8')
    preloadHasEngineApi = preloadSrc.includes(ENGINE_IPC_CHANNEL)
  } catch {
    // Source tree layout changed or file missing -- treat as not merged.
  }
  if (preloadHasEngineApi) {
    console.log(
      `preload exposes "${ENGINE_IPC_CHANNEL}" (W2-01 looks merged) -- ` +
        `visually check ${screenshotPath} for the "엔진: 연결됨" status-bar text; ` +
        'this script does not OCR the screenshot.',
    )
  } else {
    console.log(
      'W2-01 sidecar IPC not detected yet -- skipping the status-bar "연결됨" check ' +
        '(docs/briefs/W2-08.md "Defaults for ambiguity").',
    )
  }

  if (code !== 0) {
    fail(`packaged app exited with code ${code}`)
  }

  console.log('PASS: packaged app smoke check')
  process.exit(0)
})
