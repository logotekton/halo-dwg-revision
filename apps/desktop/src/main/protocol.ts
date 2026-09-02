import { extname, join, normalize, sep } from 'node:path'

// Small MIME table for the assets apps/web/dist actually produces
// (HTML/JS/CSS/JSON/images/fonts/wasm). Extend as new asset types show up.
const MIME_TYPES: Readonly<Record<string, string>> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.wasm': 'application/wasm',
  '.map': 'application/json; charset=utf-8',
}

export function getMimeType(filePath: string): string {
  return MIME_TYPES[extname(filePath).toLowerCase()] ?? 'application/octet-stream'
}

/**
 * Where the `halocad://app` protocol handler should serve `apps/web/dist`
 * from, per the packaging contract (`docs/contracts/wave-2.md` "패키징"):
 *
 *   app.isPackaged ? join(resourcesPath, 'web') : join(appPath, '../web/dist')
 *
 * Packaged: electron-builder's `extraResources` copies `apps/web/dist` ->
 * `<resources>/web` (flat, no nested `dist/`) alongside the PyInstaller
 * sidecar at `<resources>/engine/` (see `apps/desktop/electron-builder.yml`).
 * Dev/unpacked (`pnpm build && pnpm --filter @halo-cad/desktop start`):
 * `apps/desktop/{package.json,out/}` sits next to `apps/web/dist` on disk,
 * so `appPath` (== `apps/desktop`) resolves it directly.
 *
 * A pure function taking Electron's `app.isPackaged` / `app.getAppPath()` /
 * `process.resourcesPath` as plain arguments (rather than importing `app`
 * here) so it stays unit-testable without mocking Electron.
 */
export function resolveWebDistDir(options: {
  isPackaged: boolean
  appPath: string
  resourcesPath: string
}): string {
  return options.isPackaged
    ? join(options.resourcesPath, 'web')
    : join(options.appPath, '..', 'web', 'dist')
}

/**
 * Resolves a `halocad://app/<pathname>` request to a file inside `distDir`
 * (apps/web/dist), rejecting anything that would escape it. Root and empty
 * paths resolve to index.html so client-side routing has a fallback.
 */
export function resolveAssetPath(distDir: string, requestPathname: string): string {
  const pathname = requestPathname === '' || requestPathname === '/' ? '/index.html' : requestPathname
  const decoded = decodeURIComponent(pathname)
  const resolvedDistDir = normalize(distDir)
  const resolved = normalize(join(resolvedDistDir, decoded))
  const isInsideDistDir = resolved === resolvedDistDir || resolved.startsWith(resolvedDistDir + sep)
  if (!isInsideDistDir) {
    throw new Error(`refusing to serve path outside web dist dir: ${requestPathname}`)
  }
  return resolved
}
