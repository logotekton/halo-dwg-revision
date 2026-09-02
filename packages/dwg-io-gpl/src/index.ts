/**
 * `@halo-cad/dwg-io-gpl` — the GPL boundary.
 *
 * `@mlightcad/libredwg-converter` and `@mlightcad/libredwg-web` are GPL-3.0.
 * CLAUDE.md rule 3 confines them to this package and to the desktop wiring in
 * `apps/desktop/src/main/ipc/convert.ts`; `tools/verify.sh` greps for any other
 * importer, and `packages/cad-core` forbids them outright in its ESLint config.
 * Everything here is a thin call into mlightcad — no CAD logic lives in this
 * package, so nothing GPL leaks into the rest of the workspace.
 *
 * See `README.md` for the licensing note.
 */

import {
  AcDbDatabaseConverterManager,
  AcDbFileType,
  type AcDbDatabaseConverterConfig,
} from '@mlightcad/data-model';
import { AcDbLibreDwgConverter } from '@mlightcad/libredwg-converter';

/** Canonical worker/wasm file names, mirrored from `AcApWorkerAssets` (spike §A). */
export const LIBREDWG_PARSER_WORKER_FILE = 'libredwg-parser-worker.js';
export const LIBREDWG_PARSER_WASM_FILE = 'libredwg-web.wasm';
export const MTEXT_RENDERER_WORKER_FILE = 'mtext-renderer-worker.js';

export interface RegisterLibreDwgConverterOptions {
  /**
   * Directory the worker assets were deployed to, without a trailing slash —
   * for example `dmcad://app/workers`. `libredwg-web.wasm` must sit next to
   * `libredwg-parser-worker.js`: the bundled worker resolves it with
   * `new URL('libredwg-web.wasm', import.meta.url)` (spike §A).
   */
  workerBaseUrl: string;
  /** Parse in a Web Worker. Default `true`; `false` is main-thread parsing. */
  useWorker?: boolean;
  /** Worker parse timeout in milliseconds. */
  timeout?: number;
  /** Progress callback forwarded to the converter. */
  progress?: AcDbDatabaseConverterConfig['progress'];
}

export interface LibreDwgRegistration {
  /** URL the converter was configured with. */
  parserWorkerUrl: string;
  /** Removes the registration again, for tests and for teardown. */
  unregister(): void;
}

function joinUrl(base: string, file: string): string {
  return `${base.replace(/\/+$/, '')}/${file}`;
}

/**
 * Registers the LibreDWG DWG converter with the mlightcad converter manager.
 *
 * **Browser only.** The parser runs in a Web Worker backed by a 9.9 MB wasm
 * module; there is no Node path in 1.14.3 (spike §C.11), so the Node tests in
 * this package only cover the exports and the asset copier.
 *
 * cad-simple-viewer deliberately does not register a DWG converter itself —
 * its own JSDoc says so, because LibreDWG is GPL. This call is that opt-in,
 * and it is the only place in the workspace that makes it.
 */
export function registerLibreDwgConverter(
  options: RegisterLibreDwgConverterOptions
): LibreDwgRegistration {
  const parserWorkerUrl = joinUrl(options.workerBaseUrl, LIBREDWG_PARSER_WORKER_FILE);
  const config: AcDbDatabaseConverterConfig = {
    parserWorkerUrl,
    useWorker: options.useWorker ?? true,
    ...(options.timeout === undefined ? {} : { timeout: options.timeout }),
    ...(options.progress === undefined ? {} : { progress: options.progress }),
  };
  AcDbDatabaseConverterManager.instance.register(
    AcDbFileType.DWG,
    new AcDbLibreDwgConverter(config)
  );
  return {
    parserWorkerUrl,
    unregister(): void {
      AcDbDatabaseConverterManager.instance.unregister(AcDbFileType.DWG);
    },
  };
}

/** True once {@link registerLibreDwgConverter} has run in this realm. */
export function isLibreDwgConverterRegistered(): boolean {
  return AcDbDatabaseConverterManager.instance.get(AcDbFileType.DWG) !== undefined;
}

/**
 * The three files {@link registerLibreDwgConverter} needs on disk, relative to
 * `workerBaseUrl`. `scripts/copy-worker-assets.mjs` puts them there.
 */
export const WORKER_ASSET_FILES = [
  LIBREDWG_PARSER_WORKER_FILE,
  LIBREDWG_PARSER_WASM_FILE,
  MTEXT_RENDERER_WORKER_FILE,
] as const;
