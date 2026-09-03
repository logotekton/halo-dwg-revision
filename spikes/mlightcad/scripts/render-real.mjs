/**
 * W3-09 — render a real drawing through the full viewer and screenshot it.
 *
 * The fidelity half of the task: `bench-real.mjs` measures what the parser
 * *counts*, this measures what the user would *see* (WebGL/three via
 * `AcApDocManager.openDocument`), so the PNG can be put next to the office's own
 * PDF page of the same sheet.
 *
 *   node scripts/render-real.mjs --manifest <m.json> --ids S038,S034 \
 *        --out-dir <dir> [--settle 8000] [--width 2000] [--height 1400]
 *
 * PNGs land in `--out-dir` (samples/_reports/render, gitignored — a render of a
 * real drawing is drawing content and never enters the repo).
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

function parseArgs(argv) {
  const a = { ids: [], settle: 8000, width: 2000, height: 1400, timeout: 240, all: false, screenshot: true, redo: false };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--manifest') a.manifest = resolve(argv[++i]);
    else if (k === '--ids') a.ids = argv[++i].split(',').filter(Boolean);
    else if (k === '--out-dir') a.outDir = resolve(argv[++i]);
    else if (k === '--settle') a.settle = Number(argv[++i]);
    else if (k === '--width') a.width = Number(argv[++i]);
    else if (k === '--height') a.height = Number(argv[++i]);
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
    else if (k === '--all') a.all = true;
    else if (k === '--no-screenshot') a.screenshot = false;
    else if (k === '--redo') a.redo = true;
    else if (k === '--zoom-text') a.zoomText = Number(argv[++i]);
    else if (k === '--zoom-expand') a.zoomExpand = Number(argv[++i]);
    else if (k === '--suffix') a.suffix = argv[++i];
    else if (k === '--zoom-box') a.zoomBox = argv[++i].split(',').map(Number);
    else throw new Error(`unknown argument: ${k}`);
  }
  if (!a.manifest || !a.outDir || (a.ids.length === 0 && !a.all))
    throw new Error('--manifest, --out-dir and either --ids or --all are required');
  return a;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const args = parseArgs(process.argv.slice(2));
const manifest = JSON.parse(readFileSync(args.manifest, 'utf8'));
mkdirSync(args.outDir, { recursive: true });
// One JSONL line per drawing: a renderer crash kills the page, not the record,
// and a re-run resumes instead of starting the sweep over.
const jsonl = join(args.outDir, 'render.jsonl');
const done = new Set();
if (existsSync(jsonl) && !args.redo) {
  for (const l of readFileSync(jsonl, 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try {
      done.add(JSON.parse(l).id);
    } catch {
      /* torn line */
    }
  }
}
const wanted = (args.all ? Object.keys(manifest) : args.ids).filter((id) => !done.has(id));

process.env.BENCH_MANIFEST = args.manifest;
process.env.BENCH_SINK_DIR = args.outDir;
const { createServer } = await import('vite');
const server = await createServer({ root: ROOT, logLevel: 'warn', server: { port: 0, strictPort: false } });
await server.listen();
const port = server.httpServer.address().port;
const base = `http://localhost:${port}`;
for (let i = 0; i < 240; i++) {
  try {
    if ((await fetch(`${base}/bench.html`)).ok) break;
  } catch {
    /* not up yet */
  }
  await sleep(250);
}

const report = [];
try {
  for (const id of wanted) {
    const abs = manifest[id];
    if (!abs) {
      report.push({ id, ok: false, error: 'not in manifest' });
      continue;
    }
    // A fresh browser per drawing: a renderer crash leaves the previous browser
    // in a state where the next page load hangs, and it also keeps peak RSS
    // attributable to one drawing.
    const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
    const page = await browser.newPage({
      viewport: { width: args.width, height: args.height },
      deviceScaleFactor: 1,
    });
    const messages = [];
    page.on('console', (m) => messages.push(`${m.type()}: ${m.text()}`.slice(0, 240)));
    page.on('pageerror', (e) => messages.push(`pageerror: ${String(e).slice(0, 240)}`));
    const row = { id, file: abs.split('/').pop() };
    try {
      await page.goto(`${base}/bench.html`, { waitUntil: 'load' });
      await page.waitForFunction(() => window.__bench?.ready === true, null, { timeout: 120_000 });
      const url = `${base}/real/${id}${extname(abs).toLowerCase()}`;
      const r = await Promise.race([
        page.evaluate(([u, s]) => window.__bench.render(u, s), [url, args.settle]),
        sleep(args.timeout * 1000).then(() => ({ ok: false, error: `timeout after ${String(args.timeout)}s` })),
      ]);
      row.render = r;
      if (r.ok && args.zoomBox) {
        row.zoom = await page.evaluate((b) => window.__bench.zoomBox(b[0], b[1], b[2], b[3]), args.zoomBox);
        await sleep(3000);
      }
      if (r.ok && args.zoomText !== undefined) {
        row.zoom = await page.evaluate(
          ([nth, exp]) => window.__bench.zoomToText(nth, exp),
          [args.zoomText, args.zoomExpand ?? 40]
        );
        await sleep(2500);
      }
      if (args.screenshot) {
        const png = join(args.outDir, `${id}${args.suffix ?? ''}.viewer.png`);
        await page.locator('#cad').screenshot({ path: png });
        row.png = png;
      }
      row.ok = r.ok === true;
    } catch (e) {
      row.error = String(e?.message ?? e).slice(0, 400);
    }
    // The renderer's own warnings name every font it could not resolve.
    row.fontWarnings = messages.filter((m) => /font|shx|ttf|glyph/i.test(m)).slice(0, 40);
    row.messages = messages.slice(-30);
    report.push(row);
    appendFileSync(jsonl, `${JSON.stringify(row)}\n`);
    process.stderr.write(`[render-real] ${id} ${row.ok ? 'ok' : `FAIL ${row.error ?? row.render?.error ?? ''}`}\n`);
    await browser.close().catch(() => {});
  }
} finally {
  await Promise.race([server.close(), sleep(5000)]);
}
process.stdout.write(`${jsonl}: +${String(report.length)} rows\n`);
process.exit(0);
