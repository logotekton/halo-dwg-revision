#!/usr/bin/env node
/**
 * Copies the three worker assets mlightcad needs at runtime into a deployment
 * directory:
 *
 *   libredwg-parser-worker.js   @mlightcad/libredwg-converter  (GPL)
 *   libredwg-web.wasm           @mlightcad/libredwg-converter  (GPL)
 *   mtext-renderer-worker.js    @mlightcad/mtext-renderer      (MIT)
 *
 * The wasm has to land next to the worker: the bundled worker resolves it with
 * `new URL('libredwg-web.wasm', import.meta.url)` and it is not inlined
 * (docs/spikes/mlightcad-api.md §A). Everything ends up flat in one directory
 * for that reason.
 *
 * Usage:
 *   node scripts/copy-worker-assets.mjs <target-dir> [--dry-run] [--quiet]
 *
 * Typically wired into an electron-vite / Vite build step that points at the
 * renderer's `public/workers` (or `dmcad://app/workers`) directory.
 */

import { createRequire } from 'node:module';
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const HERE = dirname(fileURLToPath(import.meta.url));

/**
 * Locates a dependency's root directory.
 *
 * Resolution starts at this package so pnpm's isolated layout is honoured
 * (`node-linker=isolated`): the dependency lives under
 * `packages/dwg-io-gpl/node_modules`, not under the workspace root. Neither
 * mlightcad package lists `./package.json` in its `exports` map, so the entry
 * point is resolved instead and the tree is walked up to the directory that
 * declares the package.
 */
function packageDir(name) {
  const from = resolve(HERE, '..');
  let directory = dirname(require.resolve(name, { paths: [from] }));
  for (let depth = 0; depth < 10; depth += 1) {
    const manifest = join(directory, 'package.json');
    if (existsSync(manifest)) {
      const declared = JSON.parse(readFileSync(manifest, 'utf8')).name;
      if (declared === name) return directory;
    }
    const parent = dirname(directory);
    if (parent === directory) break;
    directory = parent;
  }
  throw new Error(`cannot locate the package root of ${name}`);
}

export const ASSETS = [
  { package: '@mlightcad/libredwg-converter', file: 'dist/libredwg-parser-worker.js', license: 'GPL-3.0' },
  { package: '@mlightcad/libredwg-converter', file: 'dist/libredwg-web.wasm', license: 'GPL-3.0' },
  { package: '@mlightcad/mtext-renderer', file: 'dist/mtext-renderer-worker.js', license: 'MIT' },
];

/**
 * Copies every asset into `targetDir`.
 *
 * @param {string} targetDir destination directory, created when missing
 * @param {{ dryRun?: boolean }} [options]
 * @returns {{ source: string, target: string, bytes: number, license: string }[]}
 */
export function copyWorkerAssets(targetDir, options = {}) {
  const destination = resolve(targetDir);
  if (!options.dryRun) mkdirSync(destination, { recursive: true });
  const copied = [];
  for (const asset of ASSETS) {
    const source = join(packageDir(asset.package), asset.file);
    const bytes = statSync(source).size;
    const target = join(destination, basename(asset.file));
    if (!options.dryRun) copyFileSync(source, target);
    copied.push({ source, target, bytes, license: asset.license });
  }
  return copied;
}

function main(argv) {
  const args = argv.filter((argument) => !argument.startsWith('--'));
  const dryRun = argv.includes('--dry-run');
  const quiet = argv.includes('--quiet');
  const targetDir = args[0];
  if (!targetDir) {
    console.error('usage: node scripts/copy-worker-assets.mjs <target-dir> [--dry-run] [--quiet]');
    process.exit(2);
  }
  const copied = copyWorkerAssets(targetDir, { dryRun });
  if (quiet) return;
  for (const entry of copied) {
    const verb = dryRun ? 'would copy' : 'copied';
    console.log(`${verb} ${basename(entry.target)} (${String(entry.bytes)} B, ${entry.license})`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  main(process.argv.slice(2));
}
