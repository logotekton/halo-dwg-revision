// posix join on purpose: these cases pass platform 'darwin', so findUvBinary
// joins with '/', and the expectation must not follow the host OS (CI runs
// this file on windows-latest too).
import { posix } from 'node:path'
import { describe, expect, it } from 'vitest'

const join = (...parts: string[]): string => posix.join(...parts)
import { engineSpawnOptions, findUvBinary, resolveEngineCommand } from './spawn'

describe('findUvBinary', () => {
  it('finds uv on PATH', () => {
    const found = findUvBinary({
      pathEnv: ['/usr/bin', '/opt/homebrew/bin'].join(':'),
      homeDir: '/home/dev',
      platform: 'darwin',
      fileExists: (p) => p === '/opt/homebrew/bin/uv',
    })
    expect(found).toBe('/opt/homebrew/bin/uv')
  })

  it('falls back to $HOME/.local/bin/uv when not on PATH', () => {
    const found = findUvBinary({
      pathEnv: '/usr/bin:/bin',
      homeDir: '/home/dev',
      platform: 'darwin',
      fileExists: (p) => p === join('/home/dev', '.local', 'bin', 'uv'),
    })
    expect(found).toBe(join('/home/dev', '.local', 'bin', 'uv'))
  })

  it('returns null when uv is nowhere to be found', () => {
    const found = findUvBinary({ pathEnv: '/usr/bin:/bin', homeDir: '/home/dev', platform: 'darwin', fileExists: () => false })
    expect(found).toBeNull()
  })

  it('looks for uv.exe on win32', () => {
    const found = findUvBinary({
      pathEnv: String.raw`C:\tools`,
      homeDir: String.raw`C:\Users\dev`,
      platform: 'win32',
      fileExists: (p) => p === String.raw`C:\tools\uv.exe`,
    })
    expect(found).toBe(String.raw`C:\tools\uv.exe`)
  })
})

describe('resolveEngineCommand', () => {
  const baseDevOptions = {
    isPackaged: false,
    engineDir: '/repo/engine',
    resourcesPath: '/unused',
    dataDir: '/data/engine',
    homeDir: '/home/dev',
    platform: 'darwin' as NodeJS.Platform,
    pathEnv: '/usr/bin',
  }

  it('dev mode: runs `uv run halo-engine serve --data-dir <dataDir>` in cwd=engineDir', () => {
    const result = resolveEngineCommand({ ...baseDevOptions, fileExists: (p) => p === '/usr/bin/uv' })
    expect(result).toEqual({
      ok: true,
      command: '/usr/bin/uv',
      args: ['run', 'halo-engine', 'serve', '--data-dir', '/data/engine'],
      cwd: '/repo/engine',
    })
  })

  it('dev mode: appends --port when a stable port is already known (restart)', () => {
    const result = resolveEngineCommand({ ...baseDevOptions, port: 54213, fileExists: (p) => p === '/usr/bin/uv' })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.args).toEqual(['run', 'halo-engine', 'serve', '--data-dir', '/data/engine', '--port', '54213'])
    }
  })

  it('dev mode: fails with the Korean guidance message when uv is missing', () => {
    const result = resolveEngineCommand({ ...baseDevOptions, fileExists: () => false })
    expect(result).toEqual({ ok: false, message: 'uv가 설치되어 있지 않습니다.' })
  })

  it('never puts the token in argv (no --token anywhere)', () => {
    const result = resolveEngineCommand({ ...baseDevOptions, fileExists: (p) => p === '/usr/bin/uv' })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.args.some((a) => a.includes('token'))).toBe(false)
    }
  })

  it('packaged mode: runs <resourcesPath>/engine/halo-engine directly', () => {
    const result = resolveEngineCommand({
      isPackaged: true,
      engineDir: '/unused',
      resourcesPath: '/Applications/Halo CAD.app/Contents/Resources',
      dataDir: '/data/engine',
      homeDir: '/home/dev',
      platform: 'darwin',
      pathEnv: '/usr/bin',
      fileExists: (p) => p === '/Applications/Halo CAD.app/Contents/Resources/engine/halo-engine',
    })
    expect(result).toEqual({
      ok: true,
      command: '/Applications/Halo CAD.app/Contents/Resources/engine/halo-engine',
      args: ['serve', '--data-dir', '/data/engine'],
      cwd: '/Applications/Halo CAD.app/Contents/Resources/engine',
    })
  })

  it('packaged mode: fails with a message naming the missing binary path', () => {
    const result = resolveEngineCommand({
      isPackaged: true,
      engineDir: '/unused',
      resourcesPath: '/res',
      dataDir: '/data/engine',
      homeDir: '/home/dev',
      platform: 'darwin',
      pathEnv: '/usr/bin',
      fileExists: () => false,
    })
    expect(result).toEqual({ ok: false, message: '엔진 실행 파일을 찾을 수 없습니다: /res/engine/halo-engine' })
  })

  it('packaged mode on win32: looks for halo-engine.exe', () => {
    const result = resolveEngineCommand({
      isPackaged: true,
      engineDir: '/unused',
      resourcesPath: String.raw`C:\Program Files\Halo CAD\resources`,
      dataDir: String.raw`C:\data\engine`,
      homeDir: String.raw`C:\Users\dev`,
      platform: 'win32',
      pathEnv: String.raw`C:\tools`,
      fileExists: (p) => p === String.raw`C:\Program Files\Halo CAD\resources\engine\halo-engine.exe`,
    })
    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.command).toBe(String.raw`C:\Program Files\Halo CAD\resources\engine\halo-engine.exe`)
    }
  })
})

describe('engineSpawnOptions', () => {
  it('hides the console window on win32 and does not detach', () => {
    expect(engineSpawnOptions('win32')).toEqual({ windowsHide: true, detached: false })
  })

  it('detaches into its own process group on darwin and does not set windowsHide', () => {
    expect(engineSpawnOptions('darwin')).toEqual({ windowsHide: false, detached: true })
  })

  it('detaches into its own process group on linux and does not set windowsHide', () => {
    expect(engineSpawnOptions('linux')).toEqual({ windowsHide: false, detached: true })
  })
})
