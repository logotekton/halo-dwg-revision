/**
 * W1-04 spike — stage worker + wasm assets into public/workers/.
 *
 * Both worker bundles resolve their siblings from `import.meta.url`, so
 * `libredwg-parser-worker.js` and `libredwg-web.wasm` MUST land in the same
 * directory. Vite serves `public/` at the site root, which is the browser
 * equivalent of what electron-vite has to do for the `dmcad://` scheme.
 *
 * Run: node scripts/copy-worker-assets.mjs   (also runs from predev/prebuild)
 */
import { copyFileSync, mkdirSync, statSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const NM = resolve(HERE, '..', 'node_modules', '@mlightcad');
const DEST = resolve(HERE, '..', 'public', 'workers');

// Names come from @mlightcad/cad-simple-viewer/lib/app/AcApWorkerAssets.d.ts
const ASSETS = [
  ['mtext-renderer/dist/mtext-renderer-worker.js', 'mtext-renderer-worker.js'],
  ['libredwg-converter/dist/libredwg-parser-worker.js', 'libredwg-parser-worker.js'],
  ['libredwg-converter/dist/libredwg-web.wasm', 'libredwg-web.wasm'],
];

mkdirSync(DEST, { recursive: true });
for (const [from, to] of ASSETS) {
  const src = resolve(NM, from);
  const dst = resolve(DEST, to);
  copyFileSync(src, dst);
  const sha = createHash('sha256').update(readFileSync(dst)).digest('hex').slice(0, 16);
  console.log(`workers/${to}  ${statSync(dst).size} bytes  sha256:${sha}…`);
}
