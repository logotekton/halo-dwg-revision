/**
 * W3-09 — browser path over the *real* drawing set (`samples/2026-09-02-실시도서`).
 *
 * Same harness as `bench-browser.mjs` (headless Chromium, libredwg-web WASM
 * worker, `AcDbDatabase.dxfOut()`, process-tree RSS sampling) with three
 * changes the real set forces:
 *
 *   1. Files are addressed by **id**, not name. Real file names carry spaces,
 *      `#` and Hangul, and the source folder is read-only and outside the repo,
 *      so `tools/bench-open.mjs` writes a manifest `{ id: absolutePath }` and
 *      the dev server streams it at `/real/<id>` (vite.config.ts). Nothing
 *      outside the manifest is reachable and nothing is copied.
 *   2. Results are appended to a **JSONL** file, one line per file, so a run
 *      that is interrupted (or budgeted, see `--budget-ms`) keeps everything it
 *      already measured and the next run resumes.
 *   3. `window.__bench.survey()` is called after the parse, so a drawing whose
 *      content lives in a layout is not reported as empty.
 *
 *   node scripts/bench-real.mjs --manifest <m.json> --out <rows.jsonl> \
 *        --sink-dir <dir> [--ids S001,S002] [--budget-ms 150000] [--redo]
 */
import { execFileSync } from 'node:child_process';
import { appendFileSync, existsSync, mkdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, extname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

function parseArgs(argv) {
  const a = { ids: [], timeout: 300, settle: 1500, budgetMs: 0, redo: false, render: false, sinkLimit: 0 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--manifest') a.manifest = resolve(argv[++i]);
    else if (k === '--out') a.out = resolve(argv[++i]);
    else if (k === '--sink-dir') a.sinkDir = resolve(argv[++i]);
    else if (k === '--ids') a.ids = argv[++i].split(',').filter(Boolean);
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
    else if (k === '--settle') a.settle = Number(argv[++i]);
    else if (k === '--budget-ms') a.budgetMs = Number(argv[++i]);
    else if (k === '--redo') a.redo = true;
    else if (k === '--sink-limit') a.sinkLimit = Number(argv[++i]);
    else if (k === '--render') a.render = true;
    else throw new Error(`unknown argument: ${k}`);
  }
  for (const need of ['manifest', 'out', 'sinkDir']) {
    if (!a[need]) throw new Error(`--${need.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)} is required`);
  }
  return a;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const CHROMIUM = /chrome|chromium/i;

function treeRss(root) {
  let text;
  try {
    text = execFileSync('/bin/ps', ['-axo', 'pid=,ppid=,rss=,comm='], { encoding: 'utf8' });
  } catch {
    return null;
  }
  const kids = new Map();
  const rss = new Map();
  const comm = new Map();
  for (const l of text.split('\n')) {
    const m = /^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/.exec(l);
    if (!m) continue;
    const [pid, ppid, kb] = [Number(m[1]), Number(m[2]), Number(m[3])];
    rss.set(pid, kb * 1024);
    comm.set(pid, m[4]);
    if (!kids.has(ppid)) kids.set(ppid, []);
    kids.get(ppid).push(pid);
  }
  if (!rss.has(root)) return null;
  let total = 0;
  let largest = 0;
  let procs = 0;
  const stack = [root];
  while (stack.length) {
    const pid = stack.pop();
    if (CHROMIUM.test(comm.get(pid) ?? '')) {
      const v = rss.get(pid) ?? 0;
      total += v;
      procs++;
      if (v > largest) largest = v;
    }
    for (const c of kids.get(pid) ?? []) stack.push(c);
  }
  return { total, largest, procs };
}

class RssSampler {
  constructor(pid, intervalMs = 150) {
    this.samples = [];
    this.timer = setInterval(() => {
      const s = treeRss(pid);
      if (s && s.procs > 0) this.samples.push({ t: Date.now(), ...s });
    }, intervalMs);
  }
  stop() {
    clearInterval(this.timer);
  }
  peak(t0, t1) {
    const inWindow = this.samples.filter((s) => s.t >= t0 && s.t <= t1);
    const use = inWindow.length ? inWindow : this.samples;
    if (!use.length) return null;
    return {
      totalRssBytes: Math.max(...use.map((s) => s.total)),
      largestProcRssBytes: Math.max(...use.map((s) => s.largest)),
      samples: use.length,
    };
  }
}

async function startVite(sinkDir, manifestPath) {
  process.env.BENCH_SINK_DIR = sinkDir;
  process.env.BENCH_MANIFEST = manifestPath;
  const { createServer } = await import('vite');
  const server = await createServer({ root: ROOT, logLevel: 'warn', server: { port: 0, strictPort: false } });
  await server.listen();
  const addr = server.httpServer?.address();
  if (!addr || typeof addr === 'string') throw new Error('vite did not report a port');
  const base = `http://localhost:${addr.port}`;
  for (let i = 0; i < 240; i++) {
    try {
      const r = await fetch(`${base}/bench.html`);
      if (r.ok) return { server, base };
    } catch {
      /* not up yet */
    }
    await sleep(250);
  }
  await server.close();
  throw new Error(`vite dev server did not answer on ${base}`);
}

async function runOne(id, absPath, base, args, handle) {
  // The page picks its converter from the URL's extension, so the real file's
  // extension has to survive the id indirection (a `.DWG` opened as DXF parses
  // to an empty database with `lastOpenError === null` — measured, W3-09).
  const url = `${base}/real/${id}${extname(absPath).toLowerCase()}`;
  const sink = `${id}.dxf`;
  const row = { id, path: 'browser', inputBytes: statSync(absPath).size, ok: false };
  const t0run = Date.now();
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  handle.browser = browser;
  const sampler = new RssSampler(process.pid);
  const consoleLines = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    page.on('console', (m) => consoleLines.push(`${m.type()}: ${m.text()}`.slice(0, 240)));
    page.on('pageerror', (e) => consoleLines.push(`pageerror: ${String(e).slice(0, 240)}`));
    page.on('crash', () => consoleLines.push('PAGE CRASHED (renderer OOM?)'));
    await page.goto(`${base}/bench.html`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__bench?.ready === true, null, { timeout: 120_000 });
    row.baselineRssBytes = sampler.peak(0, Date.now())?.totalRssBytes ?? null;
    if (args.sinkLimit) await page.evaluate((n) => window.__bench.setSinkLimit(n), args.sinkLimit);

    const all = await page.evaluate(([u, s, ms]) => window.__bench.runAll(u, s, ms), [url, sink, args.settle]);
    const m = all.marks;
    row.fetchMs = (m.fetched ?? m.start) - m.start;
    row.parse = all.parse;
    row.recount = all.recount;
    row.dxfOut = all.dxfOut;
    row.parseRssBytes = sampler.peak(m.fetched ?? m.start, m.parsed ?? Date.now())?.totalRssBytes ?? null;
    if (all.parse?.ok) {
      row.survey = await page.evaluate(() => window.__bench.survey());
    }
    row.ok = all.parse?.ok === true;
    if (all.error) row.error = all.error;
    if (!row.ok && all.parse?.error) row.error = all.parse.error;
  } catch (e) {
    row.error = String(e?.message ?? e).slice(0, 600);
  } finally {
    sampler.stop();
    const peak = sampler.peak(0, Date.now());
    row.peakRssBytes = peak?.totalRssBytes ?? null;
    row.peakLargestProcRssBytes = peak?.largestProcRssBytes ?? null;
    row.console = consoleLines.slice(-12);
    row.totalMs = Date.now() - t0run;
    await browser.close().catch(() => {});
  }
  return row;
}

// --------------------------------------------------------------------------
const args = parseArgs(process.argv.slice(2));
const manifest = JSON.parse(readFileSync(args.manifest, 'utf8'));
mkdirSync(args.sinkDir, { recursive: true });
mkdirSync(dirname(args.out), { recursive: true });

const done = new Set();
if (existsSync(args.out) && !args.redo) {
  for (const l of readFileSync(args.out, 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try {
      done.add(JSON.parse(l).id);
    } catch {
      /* a torn last line from a killed run: ignore it */
    }
  }
}
const wanted = (args.ids.length ? args.ids : Object.keys(manifest)).filter((id) => !done.has(id));
if (wanted.length === 0) {
  process.stderr.write(`[bench-real] nothing to do (${String(done.size)} rows already in ${args.out})\n`);
  process.exit(0);
}

const started = Date.now();
const { server, base } = await startVite(args.sinkDir, args.manifest);
process.stderr.write(`[bench-real] vite ${base}, ${String(wanted.length)} pending\n`);
let n = 0;
try {
  for (const id of wanted) {
    if (args.budgetMs && Date.now() - started > args.budgetMs) {
      process.stderr.write(`[bench-real] budget reached, stopping after ${String(n)} files\n`);
      break;
    }
    const handle = { browser: null };
    const deadline = sleep(args.timeout * 1000).then(async () => {
      await handle.browser?.close().catch(() => {});
      return { id, path: 'browser', ok: false, error: `timeout after ${String(args.timeout)}s` };
    });
    const row = await Promise.race([runOne(id, manifest[id], base, args, handle), deadline]);
    appendFileSync(args.out, `${JSON.stringify(row)}\n`);
    n++;
    process.stderr.write(
      `[bench-real] ${id} ${row.ok ? 'ok' : `FAIL ${row.error ?? '?'}`.slice(0, 90)} ` +
        `${String(row.parse?.entityCount ?? '-')} ents ${String(Math.round((row.totalMs ?? 0) / 1000))}s\n`
    );
  }
} finally {
  await Promise.race([server.close(), sleep(5000)]);
}
process.stderr.write(`[bench-real] wrote ${String(n)} rows to ${args.out}\n`);
process.exit(0);
