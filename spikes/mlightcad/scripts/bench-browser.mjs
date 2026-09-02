/**
 * W2-06 — path (a) driver: headless Chromium + the libredwg-web WASM worker.
 *
 * Starts the spike's Vite dev server, opens `bench.html`, and runs one file per
 * fresh browser context, sampling the RSS of the **whole Chromium process tree**
 * (browser + renderer + GPU + the wasm worker's utility process) with `ps` every
 * 150 ms. `performance.memory` is deliberately not used: it is clamped and
 * reported a zero delta in W1-04 (docs/spikes/mlightcad-api.md C.12), and the
 * brief requires process RSS.
 *
 *   node scripts/bench-browser.mjs --files F06.dwg,F11.dxf [--render] \
 *        [--dxfout] [--report out/bench/browser.json] [--timeout 900]
 *
 * `--files` names files inside the repo's fixtures/generated/ (served by the
 * dev server at /gen/<name>, streamed -- see vite.config.ts).
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, statSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { createServer } from 'vite';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const OUT = resolve(ROOT, 'out', 'bench');
const GENERATED = resolve(ROOT, '..', '..', 'fixtures', 'generated');
let BASE = '';

function parseArgs(argv) {
  const a = { files: [], render: false, dxfout: false, timeout: 900, settle: 4000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--files') a.files = argv[++i].split(',').filter(Boolean);
    else if (k === '--report') a.report = argv[++i];
    else if (k === '--render') a.render = true;
    else if (k === '--dxfout') a.dxfout = true;
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
    else if (k === '--settle') a.settle = Number(argv[++i]);
    else throw new Error(`unknown argument: ${k}`);
  }
  if (a.files.length === 0) throw new Error('--files is required');
  return a;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// --------------------------------------------------------------------------
// process-tree RSS sampling (macOS `ps`)
// --------------------------------------------------------------------------
/** Chromium's own executable name, so the Node/Vite side is never counted. */
const CHROMIUM = /chrome|chromium/i;

/**
 * RSS of every Chromium process descended from `root`, from one `ps` snapshot.
 * `root` is this driver process: Playwright's browser processes are its
 * grandchildren, and filtering by executable name keeps Node and the in-process
 * Vite server out of the total.
 */
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
  /** Peak of the samples inside [t0, t1]; falls back to the nearest sample. */
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

// --------------------------------------------------------------------------
// dev server lifecycle
// --------------------------------------------------------------------------
/**
 * In-process Vite dev server on an OS-assigned port.
 *
 * Not `spawn('vite')`: the spike's vite.config.ts pins port 5178 with
 * `strictPort`, so back-to-back driver runs fight over a port that is still in
 * TIME_WAIT and the second one stalls. Running in-process also keeps the
 * server's memory inside *this* Node process, well away from the Chromium tree
 * whose RSS we are sampling.
 */
async function startVite() {
  const server = await createServer({
    root: ROOT,
    logLevel: 'warn',
    server: { port: 0, strictPort: false },
  });
  await server.listen();
  const addr = server.httpServer?.address();
  if (!addr || typeof addr === 'string') throw new Error('vite did not report a port');
  BASE = `http://localhost:${addr.port}`;
  for (let i = 0; i < 120; i++) {
    try {
      const r = await fetch(`${BASE}/bench.html`);
      if (r.ok) return server;
    } catch {
      /* not up yet */
    }
    await sleep(250);
  }
  await server.close();
  throw new Error(`vite dev server did not answer on ${BASE}`);
}

// --------------------------------------------------------------------------
// one file, one fresh browser
// --------------------------------------------------------------------------
async function runFile(name, args, handle) {
  const url = `${BASE}/gen/${name}`;
  const row = {
    path: 'browser',
    file: name,
    inputBytes: statSync(resolve(GENERATED, name)).size,
    ok: false,
  };

  const t0run = Date.now();
  const browser = await chromium.launch({
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  handle.browser = browser;
  // Sample from this driver process down: Playwright's browser processes are
  // descendants of it, and treeRss() keeps only the Chromium ones.
  const sampler = new RssSampler(process.pid);
  row.launchMs = Date.now() - t0run;
  const consoleLines = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
    page.on('console', (m) => consoleLines.push(`${m.type()}: ${m.text()}`.slice(0, 300)));
    page.on('pageerror', (e) => consoleLines.push(`pageerror: ${String(e).slice(0, 300)}`));
    page.on('crash', () => consoleLines.push('PAGE CRASHED (renderer OOM?)'));

    await page.goto(`${BASE}/bench.html`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.__bench?.ready === true, null, { timeout: 60_000 });
    const baseline = sampler.peak(0, Date.now());
    row.baselineRssBytes = baseline?.totalRssBytes ?? null;

    if (args.render) {
      const t0 = Date.now();
      row.render = await page.evaluate(
        ([u, s]) => window.__bench.render(u, s),
        [url, args.settle]
      );
      row.render.window = [t0, Date.now()];
      row.render.rss = sampler.peak(t0, Date.now());
    } else {
      // Keep the source extension in the name: F06.dwg and F06.dxf are two
      // different runs and must not overwrite each other's output.
      const sink = `${name.replace(/\./g, '_')}.browser.dxf`;
      const all = await page.evaluate(
        ([u, s]) => window.__bench.runAll(u, s, 2000),
        [url, sink]
      );
      const m = all.marks;
      row.fetch = all.fetch ? { ...all.fetch, ms: (m.fetched ?? 0) - m.start, rss: sampler.peak(m.start, m.fetched ?? Date.now()) } : undefined;
      row.parse = all.parse
        ? { ...all.parse, rss: sampler.peak(m.fetched ?? m.start, m.parsed ?? Date.now()) }
        : { ok: false, error: all.error ?? 'parse did not run' };
      row.recount = all.recount;
      if (all.dxfOut) {
        row.dxfOut = { ...all.dxfOut, rss: sampler.peak(m.recounted ?? m.start, m.wrote ?? Date.now()) };
        if (all.dxfOut.ok) row.dxfOut.file = resolve(OUT, sink);
      }
      row.ok = all.parse?.ok === true;
      if (all.error) row.error = all.error;
    }
    if (args.render) row.ok = row.render.ok === true;
  } catch (e) {
    row.error = String(e?.message ?? e).slice(0, 600);
  } finally {
    sampler.stop();
    row.peakRssBytes = sampler.peak(0, Date.now())?.totalRssBytes ?? null;
    row.peakLargestProcRssBytes = sampler.peak(0, Date.now())?.largestProcRssBytes ?? null;
    row.console = consoleLines.slice(-25);
    row.totalMs = Date.now() - t0run;
    await browser.close().catch(() => {});
  }
  return row;
}

// --------------------------------------------------------------------------
const args = parseArgs(process.argv.slice(2));
mkdirSync(OUT, { recursive: true });
const vite = await startVite();
const rows = [];
try {
  for (const f of args.files) {
    process.stderr.write(`[bench-browser] ${f}${args.render ? ' (render)' : ''}\n`);
    const handle = { browser: null };
    const deadline = sleep(args.timeout * 1000).then(async () => {
      // Tear the browser down so the run really stops (and so the peak RSS we
      // report is the peak of a run that was still alive, not of a zombie).
      await handle.browser?.close().catch(() => {});
      return {
        path: 'browser',
        file: f,
        ok: false,
        error: `timeout after ${String(args.timeout)}s`,
      };
    });
    rows.push(await Promise.race([runFile(f, args, handle), deadline]));
  }
} finally {
  // Vite's close() waits on HMR websockets that the closed Chromium instances
  // never hung up, so give it a short grace period and move on.
  await Promise.race([vite.close(), sleep(5000)]);
}

const json = JSON.stringify({ tool: 'bench-browser.mjs', rows }, null, 2);
if (args.report) writeFileSync(args.report, json);
process.stdout.write(json + '\n');
// Same reason: do not let a lingering server handle keep the process alive.
process.exit(rows.every((r) => r.ok) ? 0 : 1);
