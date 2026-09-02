#!/usr/bin/env node
// Orchestrates dev mode without electron-vite's renderer pipeline (which is
// intentionally disabled, see electron.vite.config.ts): starts the
// independent apps/web Vite dev server, waits for it to accept connections,
// then runs `electron-vite dev` (main+preload build+watch, auto-launches
// Electron) with HALO_WEB_DEV_SERVER_URL pointing at it.
import { spawn } from 'node:child_process'
import net from 'node:net'

const WEB_HOST = '127.0.0.1'
const WEB_PORT = process.env.HALO_WEB_PORT ?? '5173'
const WEB_URL = `http://${WEB_HOST}:${WEB_PORT}`

/** @type {import('node:child_process').ChildProcess[]} */
const children = []

function spawnChild(command, args, extraEnv = {}) {
  const child = spawn(command, args, {
    stdio: 'inherit',
    env: { ...process.env, ...extraEnv },
  })
  children.push(child)
  return child
}

let shuttingDown = false
function killAll() {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill()
    }
  }
}

process.on('SIGINT', () => {
  killAll()
  process.exit(0)
})
process.on('SIGTERM', () => {
  killAll()
  process.exit(0)
})

function waitForPort(host, port, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.createConnection({ host, port }, () => {
        socket.end()
        resolve(undefined)
      })
      socket.on('error', () => {
        socket.destroy()
        if (Date.now() > deadline) {
          reject(new Error(`timed out waiting for ${host}:${String(port)}`))
          return
        }
        setTimeout(attempt, 200)
      })
    }
    attempt()
  })
}

const webDev = spawnChild('pnpm', [
  '--filter',
  '@halo-cad/web',
  'dev',
  '--',
  '--port',
  WEB_PORT,
  '--strictPort',
  '--host',
  WEB_HOST,
])
webDev.on('exit', (code) => {
  if (!shuttingDown && code !== 0) {
    killAll()
    process.exit(code ?? 1)
  }
})

try {
  await waitForPort(WEB_HOST, Number(WEB_PORT), 30000)
} catch (err) {
  console.error(String(err))
  killAll()
  process.exit(1)
}

const electronDev = spawnChild('pnpm', ['exec', 'electron-vite', 'dev'], {
  HALO_WEB_DEV_SERVER_URL: WEB_URL,
})
electronDev.on('exit', (code) => {
  killAll()
  process.exit(code ?? 0)
})
