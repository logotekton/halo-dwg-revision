import { join, sep } from 'node:path'
import { describe, expect, it } from 'vitest'
import { getMimeType, resolveAssetPath, resolveWebDistDir } from './protocol'

const DIST_DIR = join(sep, 'app', 'apps', 'web', 'dist')

describe('getMimeType', () => {
  it.each([
    ['index.html', 'text/html; charset=utf-8'],
    ['assets/app.js', 'text/javascript; charset=utf-8'],
    ['assets/app.css', 'text/css; charset=utf-8'],
    ['favicon.svg', 'image/svg+xml'],
    ['fonts/noto.woff2', 'font/woff2'],
  ])('maps %s to %s', (file, expected) => {
    expect(getMimeType(file)).toBe(expected)
  })

  it('falls back to application/octet-stream for unknown extensions', () => {
    expect(getMimeType('data.unknownext')).toBe('application/octet-stream')
  })
})

describe('resolveAssetPath', () => {
  it('maps the root path "/" to index.html', () => {
    expect(resolveAssetPath(DIST_DIR, '/')).toBe(join(DIST_DIR, 'index.html'))
  })

  it('maps an empty pathname to index.html', () => {
    expect(resolveAssetPath(DIST_DIR, '')).toBe(join(DIST_DIR, 'index.html'))
  })

  it('resolves nested asset paths', () => {
    expect(resolveAssetPath(DIST_DIR, '/assets/app.js')).toBe(join(DIST_DIR, 'assets', 'app.js'))
  })

  it('rejects path traversal outside the dist dir', () => {
    expect(() => resolveAssetPath(DIST_DIR, '/../../etc/passwd')).toThrow()
  })

  it('rejects an encoded traversal attempt', () => {
    expect(() => resolveAssetPath(DIST_DIR, '/%2e%2e/%2e%2e/etc/passwd')).toThrow()
  })
})

describe('resolveWebDistDir', () => {
  const APP_PATH_DEV = join(sep, 'repo', 'apps', 'desktop')
  const APP_PATH_PACKAGED = join(
    sep,
    'Applications',
    'Halo CAD.app',
    'Contents',
    'Resources',
    'app.asar',
  )
  const RESOURCES_PATH = join(sep, 'Applications', 'Halo CAD.app', 'Contents', 'Resources')

  it('dev (unpacked): resolves apps/web/dist next to the desktop app dir', () => {
    expect(
      resolveWebDistDir({
        isPackaged: false,
        appPath: APP_PATH_DEV,
        resourcesPath: RESOURCES_PATH,
      }),
    ).toBe(join(sep, 'repo', 'apps', 'web', 'dist'))
  })

  it('packaged: resolves the flat extraResources "web" dir, ignoring appPath', () => {
    expect(
      resolveWebDistDir({
        isPackaged: true,
        appPath: APP_PATH_PACKAGED,
        resourcesPath: RESOURCES_PATH,
      }),
    ).toBe(join(RESOURCES_PATH, 'web'))
  })
})
