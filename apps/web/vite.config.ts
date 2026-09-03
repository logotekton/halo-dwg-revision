import { resolve } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Both workspace packages are consumed as TypeScript sources rather than
      // through their CommonJS `dist/`. That keeps exactly one instance of the
      // mlightcad singletons in the bundle (cad-core and dwg-io-gpl must share
      // `AcDbDatabaseConverterManager`), avoids the ESM/CJS interop hazard of
      // mixing `require()`d and `import`ed copies of data-model, and removes
      // the build-order dependency on `dist/`. Their own `typecheck` scripts
      // still guard the sources.
      '@halo-cad/cad-core': resolve(__dirname, '../../packages/cad-core/src/index.ts'),
      '@halo-cad/dwg-io-gpl': resolve(__dirname, '../../packages/dwg-io-gpl/src/index.ts'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      // Three pages under one origin (docs/dev/viewer-integration.md):
      //   index.html    the shell (W3-01)
      //   viewer.html   the standalone 2D viewer harness (W3-02)
      //   convert.html  the hidden DWG converter window (W3-02)
      input: {
        index: resolve(__dirname, 'index.html'),
        viewer: resolve(__dirname, 'viewer.html'),
        convert: resolve(__dirname, 'convert.html'),
      },
      output: {
        // data-model's own modules are mutually circular (its `database/index`
        // re-exports `AcDbDatabaseConverterManager`, which imports back from
        // the index). Rollup warns that splitting such a cycle across chunks
        // "will likely lead to broken execution order" — so every mlightcad
        // module goes into one chunk, which also guarantees a single instance
        // of the five singletons the CadHost proposal tracks.
        manualChunks: (id: string) =>
          id.includes('node_modules/@mlightcad/') || id.includes('/@mlightcad+')
            ? 'mlightcad'
            : undefined,
      },
    },
  },
})
