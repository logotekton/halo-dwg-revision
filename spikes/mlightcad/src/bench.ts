/**
 * W2-06 — browser-side half of the large-file benchmark (ADR-0002 §3/§4).
 *
 * Path (a) of the brief: DWG parsed by the libredwg-web WASM worker, or DXF
 * parsed by data-model's native DXF converter, both inside headless Chromium.
 * `scripts/bench-browser.mjs` drives every step from Node and brackets each
 * awaited call with process-RSS samples (`performance.memory` is clamped in
 * Chromium and reported a zero delta in the W1-04 spike, see
 * docs/spikes/mlightcad-api.md C.12 -- so peak memory is measured from the
 * outside, per process).
 *
 * Each step is a separate `window.__bench.*` call on purpose: the driver needs
 * a wall-clock window per phase (fetch / parse / dxfOut / render) to attribute
 * the RSS peak to a phase.
 *
 * This file is spike-local instrumentation. GPL note (CLAUDE.md rule 3):
 * @mlightcad/libredwg-* is imported here and nowhere outside spikes/ or
 * packages/dwg-io-gpl/.
 */
import { AcApDocManager, AcEdOpenMode } from '@mlightcad/cad-simple-viewer';
import {
  AcDbDatabase,
  AcDbDatabaseConverterManager,
  AcDbFileType,
  type AcDbEntity,
} from '@mlightcad/data-model';
import { AcDbLibreDwgConverter } from '@mlightcad/libredwg-converter';

interface ParseResult {
  ok: boolean;
  ms: number;
  bytes: number;
  fileType: string;
  version?: string;
  entityCount?: number;
  byType?: Record<string, number>;
  layerCount?: number;
  blockCount?: number;
  lastOpenError?: unknown;
  error?: string;
}
interface DxfOutResult {
  ok: boolean;
  ms: number;
  bytes: number;
  postMs?: number;
  sink?: string;
  sinkSkipped?: boolean;
  error?: string;
}
interface RenderResult {
  ok: boolean;
  ms: number;
  entityCount?: number;
  error?: string;
}

/**
 * W3-09 -- what the *parser* (not the produced DXF) says about a real drawing:
 * per-space entity counts, so a drawing whose content lives in paper space is
 * not reported as empty, plus the table sizes the inventory needs.
 */
interface SurveyResult {
  ok: boolean;
  spaces?: Record<string, { count: number; byType: Record<string, number> }>;
  totalEntities?: number;
  layerNames?: string[];
  blockCount?: number;
  xrefBlocks?: string[];
  error?: string;
}

interface RunAllResult {
  ok: boolean;
  marks: Record<string, number>;
  fetch?: { ok: boolean; bytes: number; error?: string };
  parse?: ParseResult;
  recount?: number;
  dxfOut?: DxfOutResult;
  error?: string;
}

declare global {
  interface Window {
    __bench: {
      ready: boolean;
      fetchFile: (url: string) => Promise<{ ok: boolean; bytes: number; error?: string }>;
      parse: () => Promise<ParseResult>;
      recount: (waitMs?: number) => Promise<{ entityCount: number; byType: Record<string, number> }>;
      survey: () => SurveyResult;
      runAll: (url: string, sinkName: string, settleMs?: number) => Promise<RunAllResult>;
      dxfOut: (sinkName: string, version?: string, precision?: number) => Promise<DxfOutResult>;
      render: (url: string, settleMs?: number) => Promise<RenderResult>;
      release: () => void;
      setSinkLimit: (bytes: number) => void;
      log: string[];
    };
  }
}

const logEl = document.getElementById('log')!;
const log: string[] = [];
function line(cls: string, text: string) {
  log.push(text);
  const d = document.createElement('div');
  d.className = cls;
  d.textContent = text;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}

const base = location.origin;

/**
 * Above this, the dxfOut() result is measured but not POSTed back (see dxfOut).
 * W3-09 made it settable: one real sheet set produced a 111 MB DXF, which is
 * well inside Playwright's transport limit but past W2-06's conservative cap,
 * and skipping the sink would leave that file with no DXF for the engine to read.
 */
let sinkLimitBytes = 64 * 1024 * 1024;

// GPL boundary: the only libredwg registration in this file.
AcDbDatabaseConverterManager.instance.register(
  AcDbFileType.DWG,
  new AcDbLibreDwgConverter({
    parserWorkerUrl: `${base}/workers/libredwg-parser-worker.js`,
    useWorker: true,
    // 200 k / 1 M entity fixtures need far more than the default worker budget.
    timeout: 30 * 60 * 1000,
  })
);

// --------------------------------------------------------------------------
// state shared between the driver's steps
// --------------------------------------------------------------------------
let buffer: ArrayBuffer | undefined;
let fileType: AcDbFileType = AcDbFileType.DXF;
let db: AcDbDatabase | undefined;
let dxf: string | Uint8Array | undefined;
let docManager: AcApDocManager | undefined;

function errText(e: unknown): string {
  const err = e as { message?: string; stack?: string };
  return String(err?.stack ?? err?.message ?? e).slice(0, 600);
}

function countEntities(database: AcDbDatabase) {
  const byType: Record<string, number> = {};
  let n = 0;
  for (const e of database.tables.blockTable.modelSpace.newIterator()) {
    const t = (e as AcDbEntity).dxfTypeName;
    byType[t] = (byType[t] ?? 0) + 1;
    n++;
  }
  return { entityCount: n, byType };
}

window.__bench = {
  ready: false,
  log,

  /** Step 1 -- pull the fixture over HTTP into an ArrayBuffer (no parsing). */
  async fetchFile(url: string) {
    buffer = undefined;
    fileType = url.toLowerCase().endsWith('.dwg') ? AcDbFileType.DWG : AcDbFileType.DXF;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`HTTP ${String(res.status)} for ${url}`);
      buffer = await res.arrayBuffer();
      line('ok', `fetched ${url} (${String(buffer.byteLength)} B, ${fileType})`);
      return { ok: true, bytes: buffer.byteLength };
    } catch (e) {
      line('bad', `fetch failed: ${errText(e)}`);
      return { ok: false, bytes: 0, error: errText(e) };
    }
  },

  /**
   * Step 2 -- parse into an AcDbDatabase. DWG goes through the libredwg WASM
   * worker (which *transfers* and therefore detaches `buffer`, spike C.7), DXF
   * through data-model's built-in converter.
   */
  async parse() {
    const bytes = buffer?.byteLength ?? 0;
    const t0 = performance.now();
    try {
      if (!buffer) throw new Error('call fetchFile() first');
      db = new AcDbDatabase();
      await db.read(buffer, { readOnly: false }, fileType);
      buffer = undefined; // DWG detached it anyway; drop our reference either way
      const ms = performance.now() - t0;
      const counted = countEntities(db);
      const out: ParseResult = {
        ok: true,
        ms,
        bytes,
        fileType,
        version: String(db.version?.name ?? db.version),
        ...counted,
        layerCount: [...db.tables.layerTable.newIterator()].length,
        blockCount: [...db.tables.blockTable.newIterator()].length,
        lastOpenError: db.lastOpenError ?? null,
      };
      line('ok', `parsed ${String(counted.entityCount)} model-space entities in ${ms.toFixed(0)} ms`);
      return out;
    } catch (e) {
      const ms = performance.now() - t0;
      line('bad', `parse failed after ${ms.toFixed(0)} ms: ${errText(e)}`);
      return { ok: false, ms, bytes, fileType, error: errText(e) };
    }
  },

  /**
   * Step 2b -- recount after a settle delay.
   *
   * data-model converts entities in asynchronous batches
   * (`AcDbBatchProcessing`), so a count taken the instant `read()` resolves
   * could in principle be an undercount. This distinguishes "still streaming"
   * from "the parser really returned this many".
   */
  async recount(waitMs = 3000) {
    await new Promise((r) => setTimeout(r, waitMs));
    if (!db) return { entityCount: -1, byType: {} };
    const c = countEntities(db);
    line('warn', `recount after ${String(waitMs)} ms: ${String(c.entityCount)}`);
    return c;
  },

  /**
   * Step 2c (W3-09) -- per-space counts and table names from the *parsed*
   * database. `countEntities` walks model space only, which is right for the
   * synthetic fixtures and wrong for a real sheet set where the title block and
   * often the whole drawing live in a layout.
   */
  survey(): SurveyResult {
    if (!db) return { ok: false, error: 'call parse() first' };
    try {
      const spaces: Record<string, { count: number; byType: Record<string, number> }> = {};
      const layerNames: string[] = [];
      const xrefBlocks: string[] = [];
      let blockCount = 0;
      let totalEntities = 0;

      for (const layer of db.tables.layerTable.newIterator()) {
        layerNames.push(String((layer as { name?: string }).name ?? ''));
      }
      for (const btr of db.tables.blockTable.newIterator()) {
        blockCount++;
        const rec = btr as unknown as {
          name?: string;
          isXref?: boolean;
          pathName?: string;
          newIterator?: () => Iterable<AcDbEntity>;
        };
        const name = String(rec.name ?? '');
        if (rec.isXref === true) xrefBlocks.push(name);
        const isModel = /^\*Model_Space/i.test(name);
        const isPaper = /^\*Paper_Space/i.test(name);
        if (!isModel && !isPaper) continue;
        const key = isModel ? 'MODEL' : `PAPER:${name}`;
        const byType: Record<string, number> = {};
        let count = 0;
        try {
          for (const e of rec.newIterator?.() ?? []) {
            const t = (e as AcDbEntity).dxfTypeName;
            byType[t] = (byType[t] ?? 0) + 1;
            count++;
          }
        } catch (e) {
          byType[`<iterator-error>`] = 1;
          line('bad', `space ${key}: ${errText(e)}`);
        }
        spaces[key] = { count, byType };
        totalEntities += count;
      }
      line('ok', `survey: ${String(totalEntities)} entities across ${String(Object.keys(spaces).length)} spaces`);
      return { ok: true, spaces, totalEntities, layerNames, blockCount, xrefBlocks };
    } catch (e) {
      return { ok: false, error: errText(e) };
    }
  },

  /** Step 3 -- ADR-0002 tier-2 writer: dxfOut(), shipped back to disk. */
  async dxfOut(sinkName: string, version = 'AC1032', precision = 6) {
    const t0 = performance.now();
    try {
      if (!db) throw new Error('call parse() first');
      dxf = db.dxfOut(sinkName, precision, version);
      const ms = performance.now() - t0;
      const bytes = typeof dxf === 'string' ? new Blob([dxf]).size : dxf.byteLength;

      // Chromium echoes a request's POST body back over CDP inside
      // `Network.requestWillBeSent`, and a body past ~200 MB blows past Node's
      // 512 MB string cap in Playwright's transport (`ERR_STRING_TOO_LONG`),
      // killing the driver before any result is returned. Above the cap we
      // measure the write and report the size without shipping the bytes.
      if (bytes > sinkLimitBytes) {
        dxf = undefined;
        line('warn', `dxfOut ${String(bytes)} B in ${ms.toFixed(0)} ms (not shipped: over sink limit)`);
        return { ok: true, ms, bytes, sinkSkipped: true };
      }

      const t1 = performance.now();
      const body: BodyInit =
        typeof dxf === 'string' ? dxf : new Blob([dxf.slice().buffer as ArrayBuffer]);
      const res = await fetch(`${base}/__sink/${sinkName}`, { method: 'POST', body });
      if (!res.ok) throw new Error(`sink HTTP ${String(res.status)}`);
      dxf = undefined;
      line('ok', `dxfOut ${String(bytes)} B in ${ms.toFixed(0)} ms`);
      return { ok: true, ms, bytes, postMs: performance.now() - t1, sink: sinkName };
    } catch (e) {
      dxf = undefined;
      line('bad', `dxfOut failed: ${errText(e)}`);
      return { ok: false, ms: performance.now() - t0, bytes: 0, error: errText(e) };
    }
  },

  /**
   * Optional -- the *preview* half of ADR-0002 §4: open the file through the
   * full viewer (WebGL/three) rather than data-model alone, so the preview cap
   * is measured against what the user actually waits for.
   */
  async render(url: string, settleMs = 3000) {
    const t0 = performance.now();
    try {
      docManager ??= AcApDocManager.createInstance({
        container: document.getElementById('cad')!,
        autoResize: true,
        baseUrl: base,
        webworkerFileUrls: {
          mtextRender: `${base}/workers/mtext-renderer-worker.js`,
          dwgParser: `${base}/workers/libredwg-parser-worker.js`,
        },
        checkWorkersOnInit: true,
        builtinOpenFileDialog: false,
      })!;
      const mgr = docManager;
      await mgr.areWorkersReady();
      const res = await fetch(url);
      const buf = await res.arrayBuffer();
      const name = url.slice(url.lastIndexOf('/') + 1);
      const opened = await mgr.openDocument(name, buf, { mode: AcEdOpenMode.Write });
      if (!opened) throw new Error('openDocument returned false');
      await new Promise((r) => setTimeout(r, settleMs));
      const database = mgr.curDocument.database;
      const ms = performance.now() - t0;
      const { entityCount } = countEntities(database);
      line('ok', `rendered ${String(entityCount)} entities in ${ms.toFixed(0)} ms`);
      return { ok: true, ms, entityCount };
    } catch (e) {
      line('bad', `render failed: ${errText(e)}`);
      return { ok: false, ms: performance.now() - t0, error: errText(e) };
    }
  },

  /**
   * fetch -> parse -> recount -> dxfOut in ONE call, with wall-clock marks so
   * the driver can still attribute its RSS samples to a phase.
   *
   * Why not one CDP call per phase: on the 209 MB / 1 M entity fixture, letting
   * a rejection cross the CDP boundary killed the driver with
   * `ERR_STRING_TOO_LONG` (a >512 MB protocol message) before any result came
   * back. Everything here is caught in-page and only small values are returned.
   */
  async runAll(url: string, sinkName: string, settleMs = 2000) {
    const marks: Record<string, number> = { start: Date.now() };
    const out: RunAllResult = { ok: false, marks };
    try {
      out.fetch = await this.fetchFile(url);
      marks.fetched = Date.now();
      if (!out.fetch.ok) return out;

      out.parse = await this.parse();
      marks.parsed = Date.now();
      if (!out.parse.ok) return out;

      out.recount = (await this.recount(settleMs)).entityCount;
      marks.recounted = Date.now();

      out.dxfOut = await this.dxfOut(sinkName);
      marks.wrote = Date.now();
      out.ok = out.dxfOut.ok;
      return out;
    } catch (e) {
      out.error = errText(e);
      marks.failed = Date.now();
      return out;
    }
  },

  /** Raise or lower the dxfOut sink cap for this page (W3-09). */
  setSinkLimit(bytes: number) {
    sinkLimitBytes = bytes;
  },

  /** Drop every big reference so a follow-up run in the same tab starts clean. */
  release() {
    buffer = undefined;
    dxf = undefined;
    db = undefined;
    line('warn', 'released');
  },
};

window.__bench.ready = true;
line('ok', 'bench harness ready');
