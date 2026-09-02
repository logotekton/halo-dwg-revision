/**
 * Node-side coverage for the GPL boundary package.
 *
 * The converter itself cannot be exercised here: LibreDWG parses DWG inside a
 * Web Worker backed by a 9.9 MB wasm module and has no Node path in 3.14.3
 * (`docs/spikes/mlightcad-api.md` C.11). What is testable in Node — and what
 * the brief asks for — is that the exports exist and that the asset copier
 * really produces the three files the worker needs, wasm included.
 */

import { mkdtempSync, readdirSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { afterEach, describe, expect, it } from 'vitest';

import { ASSETS, copyWorkerAssets } from '../scripts/copy-worker-assets.mjs';
import {
  LIBREDWG_PARSER_WASM_FILE,
  LIBREDWG_PARSER_WORKER_FILE,
  MTEXT_RENDERER_WORKER_FILE,
  WORKER_ASSET_FILES,
  isLibreDwgConverterRegistered,
  registerLibreDwgConverter,
} from '../src/index';

const temporary: string[] = [];

afterEach(() => {
  for (const directory of temporary.splice(0)) rmSync(directory, { recursive: true, force: true });
});

function scratchDir(): string {
  const directory = mkdtempSync(join(tmpdir(), 'halo-dwg-assets-'));
  temporary.push(directory);
  return directory;
}

describe('exports', () => {
  it('names the three worker assets', () => {
    expect(LIBREDWG_PARSER_WORKER_FILE).toBe('libredwg-parser-worker.js');
    expect(LIBREDWG_PARSER_WASM_FILE).toBe('libredwg-web.wasm');
    expect(MTEXT_RENDERER_WORKER_FILE).toBe('mtext-renderer-worker.js');
    expect([...WORKER_ASSET_FILES]).toEqual([
      LIBREDWG_PARSER_WORKER_FILE,
      LIBREDWG_PARSER_WASM_FILE,
      MTEXT_RENDERER_WORKER_FILE,
    ]);
  });

  it('registers and unregisters the DWG converter on the mlightcad manager', () => {
    expect(isLibreDwgConverterRegistered()).toBe(false);
    const registration = registerLibreDwgConverter({ workerBaseUrl: 'dmcad://app/workers/' });
    try {
      expect(registration.parserWorkerUrl).toBe('dmcad://app/workers/libredwg-parser-worker.js');
      expect(isLibreDwgConverterRegistered()).toBe(true);
    } finally {
      registration.unregister();
    }
    expect(isLibreDwgConverterRegistered()).toBe(false);
  });
});

describe('copyWorkerAssets', () => {
  it('lists the wasm as a sibling of the parser worker', () => {
    const fromLibreDwg = ASSETS.filter((asset) => asset.package === '@mlightcad/libredwg-converter');
    expect(fromLibreDwg).toHaveLength(2);
    // Both come out of the same dist directory, which is what makes
    // `new URL('libredwg-web.wasm', import.meta.url)` resolve inside the worker.
    expect(new Set(fromLibreDwg.map((asset) => asset.file.split('/')[0])).size).toBe(1);
    expect(ASSETS.every((asset) => asset.license === 'GPL-3.0' || asset.license === 'MIT')).toBe(true);
  });

  it('copies all three files into an empty directory', () => {
    const target = scratchDir();
    const copied = copyWorkerAssets(target);
    expect(copied).toHaveLength(3);
    expect(readdirSync(target).sort()).toEqual([...WORKER_ASSET_FILES].sort());
    for (const entry of copied) {
      expect(statSync(entry.target).size).toBe(entry.bytes);
      expect(entry.bytes).toBeGreaterThan(0);
    }
    // The wasm is the big one and is not inlined into the worker.
    const wasm = copied.find((entry) => entry.target.endsWith(LIBREDWG_PARSER_WASM_FILE));
    expect(wasm?.bytes).toBeGreaterThan(1_000_000);
  });

  it('creates missing directories and is repeatable', () => {
    const target = join(scratchDir(), 'nested', 'workers');
    copyWorkerAssets(target);
    const second = copyWorkerAssets(target);
    expect(second).toHaveLength(3);
    expect(readdirSync(target).sort()).toEqual([...WORKER_ASSET_FILES].sort());
  });

  it('touches nothing in dry-run mode', () => {
    const target = join(scratchDir(), 'dry');
    const planned = copyWorkerAssets(target, { dryRun: true });
    expect(planned).toHaveLength(3);
    expect(() => readdirSync(target)).toThrow();
  });
});
