import { createReadStream, createWriteStream, mkdirSync, readFileSync, statSync } from 'node:fs';
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

// --------------------------------------------------------------------------
// W2-06 instrumentation (large-file benchmark, `scripts/bench-browser.mjs`).
// Two extra dev-server routes, both dev-only and both used by bench.html:
//   GET  /gen/<name>     stream a file out of the repo's fixtures/generated/
//                        (F11/F12 are 41 MB / 209 MB, so this streams instead
//                        of buffering the whole body in the Vite process the
//                        way `fixtureServer` does -- otherwise the server's own
//                        RSS would dwarf what we are trying to measure).
//   POST /__sink/<name>  write a request body into out/bench/<name>. The page
//                        ships its dxfOut() result back to disk this way; going
//                        through Playwright's JSON bridge for a 200 MB string
//                        is neither fast nor reliable.
// --------------------------------------------------------------------------
const GENERATED = fileURLToPath(new URL('../../fixtures/generated/', import.meta.url));
const SINK = fileURLToPath(new URL('./out/bench/', import.meta.url));
const SAFE_NAME = /^[A-Za-z0-9._-]+$/;

function benchRoutes(): Plugin {
  const mw: Connect.NextHandleFunction = (req, res, next) => {
    const url = (req.url ?? '').split('?')[0];

    if (url.startsWith('/gen/')) {
      const name = decodeURIComponent(url.slice('/gen/'.length));
      if (!SAFE_NAME.test(name)) {
        res.statusCode = 403;
        return res.end('forbidden');
      }
      const file = normalize(join(GENERATED, name));
      try {
        res.setHeader('content-type', MIME[extname(file)] ?? 'application/octet-stream');
        res.setHeader('content-length', String(statSync(file).size));
        createReadStream(file).pipe(res);
      } catch {
        res.statusCode = 404;
        res.end('not found');
      }
      return;
    }

    if (url.startsWith('/__sink/')) {
      const name = decodeURIComponent(url.slice('/__sink/'.length));
      if (req.method !== 'POST' || !SAFE_NAME.test(name)) {
        res.statusCode = 403;
        return res.end('forbidden');
      }
      mkdirSync(SINK, { recursive: true });
      const out = createWriteStream(join(SINK, name));
      req.pipe(out);
      out.on('finish', () => {
        res.setHeader('content-type', 'application/json');
        res.end(JSON.stringify({ written: name, bytes: out.bytesWritten }));
      });
      out.on('error', (e: Error) => {
        res.statusCode = 500;
        res.end(e.message);
      });
      return;
    }

    return next();
  };
  return {
    name: 'spike-bench-routes',
    configureServer: (s) => void s.middlewares.use(mw),
  };
}

// The spike lives OUTSIDE the pnpm workspace (own package.json, npm install).
// Worker + wasm assets are staged into public/workers by scripts/copy-worker-assets.mjs
// so they are served as same-origin siblings, which is what both worker bundles
// require (they resolve their wasm relative to `import.meta.url`).
export default defineConfig({
  plugins: [fixtureServer(), benchRoutes()],
  define: { __PKG__: JSON.stringify(versions) },
  server: { port: 5178, strictPort: true },
  preview: { port: 4178, strictPort: true },
  build: { target: 'es2022', chunkSizeWarningLimit: 8192 },
  optimizeDeps: { include: ['three', 'lodash-es'] },
});
