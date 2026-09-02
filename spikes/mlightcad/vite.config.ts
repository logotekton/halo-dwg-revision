import { readFileSync } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Connect, Plugin } from 'vite';
import { defineConfig } from 'vite';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as {
  dependencies: Record<string, string>;
};
const versions: Record<string, string> = {};
for (const name of Object.keys(pkg.dependencies)) {
  versions[name] = (
    JSON.parse(
      readFileSync(new URL(`./node_modules/${name}/package.json`, import.meta.url), 'utf8')
    ) as { version: string }
  ).version;
}

const FIXTURES = fileURLToPath(new URL('./fixtures/', import.meta.url));
const MIME: Record<string, string> = {
  '.dxf': 'application/dxf',
  '.dwg': 'application/acad',
  '.json': 'application/json',
};

/** Serve the committed `fixtures/` directory at `/fixtures/*` (dev + preview). */
function fixtureServer(): Plugin {
  const mw: Connect.NextHandleFunction = (req, res, next) => {
    const url = (req.url ?? '').split('?')[0];
    if (!url.startsWith('/fixtures/')) return next();
    const file = normalize(join(FIXTURES, decodeURIComponent(url.slice('/fixtures/'.length))));
    if (!file.startsWith(FIXTURES)) {
      res.statusCode = 403;
      return res.end('forbidden');
    }
    try {
      const body = readFileSync(file);
      res.setHeader('content-type', MIME[extname(file)] ?? 'application/octet-stream');
      res.end(body);
    } catch {
      res.statusCode = 404;
      res.end('not found');
    }
  };
  return {
    name: 'spike-fixture-server',
    configureServer: (s) => void s.middlewares.use(mw),
    configurePreviewServer: (s) => void s.middlewares.use(mw),
  };
}

// The spike lives OUTSIDE the pnpm workspace (own package.json, npm install).
// Worker + wasm assets are staged into public/workers by scripts/copy-worker-assets.mjs
// so they are served as same-origin siblings, which is what both worker bundles
// require (they resolve their wasm relative to `import.meta.url`).
export default defineConfig({
  plugins: [fixtureServer()],
  define: { __PKG__: JSON.stringify(versions) },
  server: { port: 5178, strictPort: true },
  preview: { port: 4178, strictPort: true },
  build: { target: 'es2022', chunkSizeWarningLimit: 8192 },
  optimizeDeps: { include: ['three', 'lodash-es'] },
});
