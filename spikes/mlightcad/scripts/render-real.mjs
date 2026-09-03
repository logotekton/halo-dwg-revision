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
import { mkdirSync, writeFileSync } from 'node:fs';
import { readFileSync } from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

function parseArgs(argv) {
  const a = { ids: [], settle: 8000, width: 2000, height: 1400, timeout: 240 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--manifest') a.manifest = resolve(argv[++i]);
    else if (k === '--ids') a.ids = argv[++i].split(',').filter(Boolean);
    else if (k === '--out-dir') a.outDir = resolve(argv[++i]);
    else if (k === '--settle') a.settle = Number(argv[++i]);
    else if (k === '--width') a.width = Number(argv[++i]);
    else if (k === '--height') a.height = Number(argv[++i]);
    else if (k === '--timeout') a.timeout = Number(argv[++i]);
    else throw new Error(`unknown argument: ${k}`);
  }
  if (!a.manifest || !a.outDir || a.ids.length === 0) throw new Error('--manifest, --ids and --out-dir are required');
  return a;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const args = parseArgs(process.argv.slice(2));
const manifest = JSON.parse(readFileSync(args.manifest, 'utf8'));
mkdirSync(args.outDir, { recursive: true });

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
const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
try {
  for (const id of args.ids) {
    const abs = manifest[id];
    if (!abs) {
      report.push({ id, ok: false, error: 'not in manifest' });
      continue;
    }
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
      const png = join(args.outDir, `${id}.viewer.png`);
      await page.locator('#cad').screenshot({ path: png });
      row.png = png;
      row.ok = r.ok === true;
    } catch (e) {
      row.error = String(e?.message ?? e).slice(0, 400);
    }
    // The renderer's own warnings name every font it could not resolve.
    row.fontWarnings = messages.filter((m) => /font|shx|ttf|glyph/i.test(m)).slice(0, 40);
    row.messages = messages.slice(-30);
    report.push(row);
    process.stderr.write(`[render-real] ${id} ${row.ok ? 'ok' : `FAIL ${row.error ?? row.render?.error ?? ''}`}\n`);
    await page.close();
  }
} finally {
  await browser.close().catch(() => {});
  await Promise.race([server.close(), sleep(5000)]);
}
writeFileSync(join(args.outDir, 'render-report.json'), JSON.stringify(report, null, 1));
process.stdout.write(`${join(args.outDir, 'render-report.json')}\n`);
process.exit(0);
