import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'

// Renderer is intentionally NOT configured here (ADR-0001 / brief W1-01):
// apps/web is a fully independent Vite app. In dev, apps/desktop/scripts/dev.mjs
// starts the apps/web dev server separately and passes its URL to the main
// process via HALO_WEB_DEV_SERVER_URL. In production, main serves
// apps/web/dist through the halocad://app custom protocol (see src/main/index.ts).
//
// `build.externalizeDeps` defaults to true for both main and preload, so
// node_modules dependencies (electron, etc.) stay external instead of being
// bundled -- no explicit plugin needed.
//
// No package.json "type": "module" is set for this package, so electron-vite
// builds both main and preload as CommonJS by default. This is deliberate:
// CJS preload output is the most broadly compatible with a sandboxed
// (sandbox: true) BrowserWindow across Electron versions.
export default defineConfig({
  main: {},
  preload: {
    build: {
      rollupOptions: {
        // Two preload entries: the main window's (W1-01) and the hidden DWG
        // converter window's (W3-02, ADR-0002 개정 §2). The converter page gets
        // its own preload so its IPC surface is exactly two channels.
        input: {
          index: resolve(__dirname, 'src/preload/index.ts'),
          convert: resolve(__dirname, 'src/preload/convert.ts'),
        },
        output: {
          entryFileNames: '[name].js',
        },
      },
    },
  },
})
