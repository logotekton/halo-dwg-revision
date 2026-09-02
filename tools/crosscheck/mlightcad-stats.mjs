#!/usr/bin/env node
/**
 * `LayerStatsDocument` producer for the mlightcad (viewer) parser.
 *
 * `@halo-cad/cad-core` deliberately ships no CLI -- it is a library the
 * renderer imports -- so `tools/crosscheck.sh` needs this thin wrapper to get
 * the third producer's document onto disk next to `halo-engine stats` and
 * `acad-bridge stats` (brief W2-04, Constraints: "cad-core에 CLI가 없으면 짧은
 * Node 스크립트 tools/crosscheck/mlightcad-stats.mjs 작성").
 *
 * Usage:
 *   node tools/crosscheck/mlightcad-stats.mjs <in.dxf> --out <json>
 *
 * Requires `pnpm --filter @halo-cad/cad-core build` first: this loads the
 * built `packages/cad-core/dist`, not the TypeScript sources. That build is
 * CommonJS (cad-core README, "개발"), hence `createRequire` rather than a
 * bare `import`.
 *
 * Output is byte-identical for identical input bytes (CLAUDE.md rule 7):
 * `JSON.stringify` with sorted keys and a trailing newline, matching what
 * `halo-engine stats` writes.
 */

import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(HERE, '..', '..');
const CAD_CORE_DIST = resolve(REPO_ROOT, 'packages', 'cad-core', 'dist', 'index.js');

const USAGE = 'usage: mlightcad-stats.mjs <in.dxf> --out <out.json>\n';

function parseArgs(argv) {
  let input;
  let out;
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === '--out') {
      out = argv[i + 1];
      i += 1;
    } else if (arg === '-h' || arg === '--help') {
      process.stdout.write(USAGE);
      process.exit(0);
    } else if (arg.startsWith('--')) {
      throw new Error(`unknown option: ${arg}`);
    } else if (input === undefined) {
      input = arg;
    } else {
      throw new Error(`unexpected argument: ${arg}`);
    }
  }
  if (input === undefined || out === undefined) throw new Error(USAGE.trim());
  return { input: resolve(input), out: resolve(out) };
}

/**
 * Recursively rebuilds `value` with object keys in ascending code-point order.
 * `JSON.stringify` preserves insertion order, so sorting has to happen here
 * for the file to be reproducible regardless of how the maps were filled.
 */
function sortKeys(value) {
  if (Array.isArray(value)) return value.map(sortKeys);
  if (value === null || typeof value !== 'object') return value;
  const out = {};
  for (const key of Object.keys(value).sort()) out[key] = sortKeys(value[key]);
  return out;
}

async function main(argv) {
  const { input, out } = parseArgs(argv);
  const require = createRequire(import.meta.url);
  let cadCore;
  try {
    cadCore = require(CAD_CORE_DIST);
  } catch (error) {
    process.stderr.write(
      `cannot load ${CAD_CORE_DIST}: run \`pnpm --filter @halo-cad/cad-core build\` first\n`
    );
    throw error;
  }
  const { openDxf, statsByLayer, dispose } = cadCore;

  const buffer = readFileSync(input);
  const fileSha256 = createHash('sha256').update(buffer).digest('hex');
  const bytes = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);

  const handle = await openDxf(bytes, { fileSha256 });
  try {
    const document = statsByLayer(handle, { file_sha256: fileSha256 });
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, `${JSON.stringify(sortKeys(document), null, 2)}\n`, 'utf8');
  } finally {
    dispose(handle);
  }
  process.stdout.write(`${out}\n`);
}

main(process.argv.slice(2)).catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(1);
});
