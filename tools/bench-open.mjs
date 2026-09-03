#!/usr/bin/env node
/**
 * W2-06 — large-file / WASM-OOM benchmark harness (ADR-0002 §3, §4).
 *
 * Measures the three candidate "open a drawing and produce the working DXF"
 * paths on the same fixtures, with wall time, peak process RSS and conversion
 * fidelity against `fixtures/truth`, and prints a markdown table.
 *
 *   node tools/bench-open.mjs --paths acad,dxfout,browser --files fixtures/generated/F06.dwg
 *   node tools/bench-open.mjs --paths acad,dxfout,engine --files fixtures/generated/F11.dxf \
 *        --heap default,16384,8192 --repeat 1
 *
 * Paths
 *   acad     packages/acad-bridge (acad-ts, MIT). DWG in -> `dwg2dxf`;
 *            DXF in -> `stats` (acad-ts's own parser, read-only open).
 *   dxfout   @mlightcad/data-model in Node CJS -> AcDbDatabase.dxfOut()
 *            (spikes/mlightcad/scripts/bench-dxfout.cjs). DXF in only: the DWG
 *            converter forces `useWorker: true` and Node has no `Worker`.
 *   browser  headless Chromium: libredwg-web WASM worker (DWG) or data-model's
 *            DXF reader, then dxfOut() (spikes/mlightcad/scripts/bench-browser.mjs).
 *   engine   the Python engine's own read (`halo-engine stats`, ezdxf) -- not a
 *            converter, but the cost that decides the "engine-only" tier.
 *   native   native LibreDWG `dwg2dxf` -- unmeasured, needs a Homebrew install.
 *
 * Memory: peak RSS comes from `/usr/bin/time -l` for the Node/Python paths and
 * from `ps` sampling of the whole Chromium process tree for the browser path
 * (`performance.memory` is clamped -- spike C.12). `--heap` re-runs the Node
 * paths under `--max-old-space-size` so a 16 GB machine can be simulated on
 * this 24 GB one.
 *
 * Output: `tools/bench/results-<YYYY-MM-DD>.json` plus the markdown table on
 * stdout. Timings and RSS are medians of `--repeat` runs.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compareStats, fidelityCell } from './bench/compare-stats.mjs';
import { enumerateSet, versionMarker } from './bench/real-set.mjs';
import { scanDxf } from './bench/scan-dxf.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ALL_PATHS = ['acad', 'dxfout', 'browser', 'engine', 'acadconv'];

// --------------------------------------------------------------------------
// args
// --------------------------------------------------------------------------
function parseArgs(argv) {
  const a = {
    paths: ['acad', 'dxfout'],
    files: [],
    repeat: 3,
    repeatLarge: 1,
    largeBytes: 20 * 1024 * 1024,
    heaps: ['default'],
    outDir: join(ROOT, 'tools', 'bench'),
    work: join(ROOT, 'tools', 'bench', 'work'),
    truthDirs: [join(ROOT, 'fixtures', 'truth'), '/tmp/truth-scratch'],
    fidelity: true,
    keep: false,
    timeout: 1800,
    browserRender: false,
    label: '',
    // W3-09 --dir mode
    dir: null,
    summary: false,
    fresh: false,
    ids: [],
    budgetMs: 0,
    reports: join(ROOT, 'samples', '_reports'),
    runBrowser: false,
  };
  const list = (v) => v.split(',').map((s) => s.trim()).filter(Boolean);
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    const next = () => argv[++i];
    if (k === '--paths') a.paths = list(next());
    else if (k === '--files') {
      // accepts `--files a,b` and `--files a b c`
      while (i + 1 < argv.length && !argv[i + 1].startsWith('--')) a.files.push(...list(argv[++i]));
    } else if (k === '--repeat') a.repeat = Number(next());
    else if (k === '--repeat-large') a.repeatLarge = Number(next());
    else if (k === '--heap') a.heaps = list(next());
    else if (k === '--out-dir') a.outDir = resolve(next());
    else if (k === '--work') a.work = resolve(next());
    else if (k === '--json') a.json = resolve(next());
    else if (k === '--truth-dir') a.truthDirs.unshift(resolve(next()));
    else if (k === '--no-fidelity') a.fidelity = false;
    else if (k === '--keep') a.keep = true;
    else if (k === '--timeout') a.timeout = Number(next());
    else if (k === '--browser-render') a.browserRender = true;
    else if (k === '--label') a.label = next();
    else if (k === '--dir') a.dir = resolve(next());
    else if (k === '--summary') a.summary = true;
    else if (k === '--fresh') a.fresh = true;
    else if (k === '--ids') a.ids = list(next());
    else if (k === '--budget-ms') a.budgetMs = Number(next());
    else if (k === '--reports') a.reports = resolve(next());
    else if (k === '--run-browser') a.runBrowser = true;
    else if (k === '--help' || k === '-h') a.help = true;
    else throw new Error(`unknown argument: ${k}`);
  }
  if (a.help) return a;
  if (a.files.length === 0 && !a.dir) throw new Error('--files or --dir is required');
  for (const p of a.paths) if (!ALL_PATHS.includes(p)) throw new Error(`unknown path: ${p}`);
  return a;
}

const USAGE = `usage: node tools/bench-open.mjs --paths ${ALL_PATHS.join(',')} --files <drawing>...
  --repeat N          runs per cell for small inputs (default 3, median reported)
  --repeat-large N    runs per cell for inputs > 20 MB (default 1)
  --heap default,8192 Node --max-old-space-size values (MB) to sweep
  --no-fidelity       skip the halo-engine stats / fixtures-truth comparison
  --browser-render    browser path opens through the full viewer instead of parse-only
  --keep              keep the converted DXF/DWG files under --work

W3-09 batch mode (a real, read-only drawing folder outside the repo):
  --dir <folder>      measure every .dwg/.dxf under <folder> (recursive, .bak skipped)
  --summary           one row per drawing instead of one row per (drawing, path)
  --ids S001,S004     restrict to these ids
  --fresh             recompute cells instead of resuming from the cell store
  --budget-ms N       stop starting new work after N ms (resumable; run again)
  --run-browser       run the Chromium/libredwg batch for ids that have no row yet
  --reports <dir>     scratch + cell store (default samples/_reports, gitignored)
`;

// --------------------------------------------------------------------------
// process runner: /usr/bin/time -l gives wall time and peak RSS on macOS
// --------------------------------------------------------------------------
function runTimed(cmd, cmdArgs, opts = {}) {
  const t0 = Date.now();
  const r = spawnSync('/usr/bin/time', ['-l', cmd, ...cmdArgs], {
    cwd: opts.cwd ?? ROOT,
    encoding: 'utf8',
    timeout: (opts.timeout ?? 1800) * 1000,
    maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, PATH: `${process.env.HOME}/.local/bin:${process.env.PATH}` },
  });
  const wallMs = Date.now() - t0;
  const stderr = r.stderr ?? '';
  const rss = /(\d+)\s+maximum resident set size/.exec(stderr);
  const real = /([\d.]+)\s+real\s/.exec(stderr);
  return {
    ok: r.status === 0,
    status: r.status,
    signal: r.signal,
    timedOut: r.error?.code === 'ETIMEDOUT',
    wallMs,
    realMs: real ? Math.round(Number(real[1]) * 1000) : wallMs,
    peakRssBytes: rss ? Number(rss[1]) : null,
    stdout: r.stdout ?? '',
    stderr,
  };
}

const median = (xs) => {
  const v = xs.filter((x) => typeof x === 'number' && Number.isFinite(x)).sort((p, q) => p - q);
  if (!v.length) return null;
  return v.length % 2 ? v[(v.length - 1) / 2] : Math.round((v[v.length / 2 - 1] + v[v.length / 2]) / 2);
};

const nodeArgs = (heap) => (heap === 'default' ? [] : [`--max-old-space-size=${heap}`]);
const stem = (f) => basename(f).replace(/\.(dxf|dwg)$/i, '');
const mb = (b) => (typeof b === 'number' ? (b / 1024 / 1024).toFixed(1) : '—');
const secs = (ms) => (typeof ms === 'number' ? (ms / 1000).toFixed(1) : '—');

// --------------------------------------------------------------------------
// fidelity: read a produced DXF with the engine (ezdxf) and diff against truth
// --------------------------------------------------------------------------
function truthFor(name, dirs) {
  for (const d of dirs) {
    const p = join(d, `${name}.json`);
    if (existsSync(p)) return p;
  }
  return null;
}

/**
 * Best-effort one-line cause from a failed run. `/usr/bin/time -l` appends its
 * own resource block to stderr, so "last line" is useless; look for a Python
 * exception, a Node error, or a V8 OOM banner instead.
 */
function causeOf(r) {
  const text = `${r.stderr}\n${r.stdout}`;
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const patterns = [
    /^[A-Za-z_][\w.]*(Error|Exception|Exit):/, // Python / Node exception line
    /JavaScript heap out of memory/,
    /Allocation failed/,
    /Killed|SIGKILL|SIGABRT/,
  ];
  for (const p of patterns) {
    const hit = lines.find((l) => p.test(l));
    if (hit) return hit.slice(0, 220);
  }
  if (r.timedOut) return 'timeout';
  if (r.signal) return `killed by ${r.signal}`;
  return `exit ${String(r.status)}`;
}

function engineStats(dxfPath, outJson, timeout) {
  const r = runTimed('uv', ['run', '--project', 'engine', 'halo-engine', 'stats', dxfPath, '--out', outJson], {
    timeout,
  });
  if (!r.ok) return { r, doc: null, error: causeOf(r) };
  return { r, doc: JSON.parse(readFileSync(outJson, 'utf8')) };
}

function fidelityOf(statsDoc, file, args) {
  const tp = truthFor(stem(file), args.truthDirs);
  if (!tp) return { error: 'no truth file' };
  return compareStats(statsDoc, JSON.parse(readFileSync(tp, 'utf8')));
}

// --------------------------------------------------------------------------
// paths
// --------------------------------------------------------------------------
function runAcad(file, heap, args, work) {
  const isDwg = file.toLowerCase().endsWith('.dwg');
  const out = join(work, `${stem(file)}.acad.${isDwg ? 'dxf' : 'json'}`);
  const cli = 'packages/acad-bridge/bin/acad-bridge.mjs';
  const argv = isDwg
    ? [...nodeArgs(heap), cli, 'dwg2dxf', file, out]
    : [...nodeArgs(heap), cli, 'stats', file, '--out', out];
  const r = runTimed(process.execPath, argv, { timeout: args.timeout });
  const res = { r, out, mode: isDwg ? 'dwg2dxf' : 'stats', producesDxf: isDwg, producesStats: !isDwg };
  if (isDwg && r.ok) {
    // Second, untimed read: what acad-ts itself thinks it read out of the DWG.
    // Needed because ezdxf may refuse the DXF acad-ts writes, and then the
    // primary fidelity cell says nothing about the *parse*.
    const selfOut = join(work, `${stem(file)}.acad-selfview.json`);
    const s = runTimed(process.execPath, [cli, 'stats', file, '--out', selfOut], { timeout: args.timeout });
    if (s.ok) res.selfView = selfOut;
  }
  return res;
}

function runDxfOut(file, heap, args, work) {
  const out = join(work, `${stem(file)}.dxfout.dxf`);
  const report = join(work, `${stem(file)}.dxfout.report.json`);
  const r = runTimed(
    process.execPath,
    [
      ...nodeArgs(heap),
      'spikes/mlightcad/scripts/bench-dxfout.cjs',
      '--in',
      resolve(ROOT, file),
      '--out',
      out,
      '--report',
      report,
    ],
    { timeout: args.timeout }
  );
  let detail = null;
  try {
    detail = JSON.parse(readFileSync(report, 'utf8'));
  } catch {
    /* the script died before writing a report */
  }
  return { r, out, detail, mode: 'dxfOut', producesDxf: r.ok };
}

function runEngine(file, args, work) {
  const out = join(work, `${stem(file)}.engine.json`);
  const r = runTimed('uv', ['run', '--project', 'engine', 'halo-engine', 'stats', resolve(ROOT, file), '--out', out], {
    timeout: args.timeout,
  });
  return { r, out, mode: 'ezdxf stats', producesStats: r.ok };
}

/**
 * One driver process for the whole browser matrix, files and repeats expanded
 * into its `--files` list.
 *
 * The driver's Vite dev server pays a cold-start module-transform cost of about
 * three minutes for the mlightcad + three.js graph, while a single measured run
 * is well under a second, so paying that once is the only sane arrangement.
 * Isolation still holds where it matters: every entry in the list gets its own
 * Chromium process tree, so no run inherits the previous run's RSS.
 */
function runBrowserAll(files, args, work) {
  const expanded = files.flatMap((f) => {
    const abs = resolve(ROOT, f);
    const runs = existsSync(abs) && statSync(abs).size > args.largeBytes ? args.repeatLarge : args.repeat;
    return Array.from({ length: runs }, () => basename(f));
  });
  const report = join(work, 'browser.report.json');
  const spike = join(ROOT, 'spikes', 'mlightcad');
  const argv = [
    'scripts/bench-browser.mjs',
    '--files',
    expanded.join(','),
    '--report',
    report,
    '--timeout',
    String(args.timeout),
    args.browserRender ? '--render' : '--dxfout',
  ];
  const r = runTimed(process.execPath, argv, { cwd: spike, timeout: args.timeout * expanded.length + 600 });
  let rows = [];
  try {
    rows = JSON.parse(readFileSync(report, 'utf8')).rows;
  } catch {
    return files.map((f) => ({ file: basename(f), ok: false, error: causeOf(r) }));
  }
  // Collapse the repeats of each file into one row carrying medians.
  const out = [];
  for (const f of files) {
    const name = basename(f);
    const attempts = rows.filter((x) => x.file === name);
    if (attempts.length === 0) {
      out.push({ file: name, ok: false, error: 'driver produced no row' });
      continue;
    }
    out.push({
      ...attempts[attempts.length - 1],
      runs: attempts.length,
      medianTotalMs: median(
        attempts.map((a) => (a.render ? a.render.ms : (a.parse?.ms ?? 0) + (a.dxfOut?.ms ?? 0)))
      ),
      medianPeakRssBytes: median(attempts.map((a) => a.peakRssBytes)),
    });
  }
  return out;
}

// --------------------------------------------------------------------------
// main
// --------------------------------------------------------------------------
const args = parseArgs(process.argv.slice(2));
if (args.help) {
  process.stdout.write(USAGE);
  process.exit(0);
}
// --------------------------------------------------------------------------
// W3-09 --dir: a whole real drawing folder, resumable
//
// The set is read-only and lives outside the repo, so every product of this
// mode goes under `--reports` (default `samples/_reports`, gitignored). Cells
// are keyed `<id>|<path>` and cached in `cells.json`: a run that is killed (or
// hits `--budget-ms`) resumes where it stopped, which is what makes a 68-file
// matrix survivable inside a 3-minute command budget.
// --------------------------------------------------------------------------
const TIER = (n) => (n == null ? '—' : n <= 250_000 ? 'A' : n <= 800_000 ? 'B' : 'C');

function loadJson(p, fallback) {
  try {
    return JSON.parse(readFileSync(p, 'utf8'));
  } catch {
    return fallback;
  }
}

function readBrowserRows(p) {
  const rows = new Map();
  if (!existsSync(p)) return rows;
  for (const line of readFileSync(p, 'utf8').split('\n')) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      rows.set(r.id, r);
    } catch {
      /* torn last line of a killed run */
    }
  }
  return rows;
}

/** acad-ts (a): read the DWG directly -- `info` for header facts, `stats` for the contract document. */
function acadCell(f, workDir, args) {
  const cli = 'packages/acad-bridge/bin/acad-bridge.mjs';
  const statsOut = join(workDir, `${f.id}.acad.json`);
  const info = runTimed(process.execPath, [cli, 'info', f.abs], { timeout: args.timeout });
  const cell = { path: 'acad', mode: 'acad-ts info+stats', versionMarker: versionMarker(f.abs) };
  if (info.ok) {
    try {
      const j = JSON.parse(info.stdout);
      cell.version = j.version;
      cell.codePage = j.code_page;
      cell.spaces = j.spaces;
      cell.infoEntityCount = j.entity_count;
    } catch {
      cell.infoParseError = true;
    }
  } else {
    cell.infoError = causeOf(info);
  }
  const st = runTimed(process.execPath, [cli, 'stats', f.abs, '--out', statsOut], { timeout: args.timeout });
  cell.ok = st.ok;
  cell.timeMs = st.realMs;
  cell.peakRssBytes = st.peakRssBytes;
  if (!st.ok) {
    cell.error = st.timedOut ? `timeout after ${String(args.timeout)}s` : causeOf(st);
    return cell;
  }
  const doc = loadJson(statsOut, null);
  if (doc) {
    cell.entityCount = doc.totals.entity_count;
    cell.textCount = doc.totals.text_count;
    cell.textHash = doc.totals.text_hash;
    cell.countByType = doc.totals.count_by_type;
    cell.insertByBlock = Object.keys(doc.totals.insert_by_block ?? {}).length;
    cell.buckets = doc.buckets.length;
    cell.layers = [...new Set(doc.buckets.map((b) => b.layer))].length;
    cell.spacesSeen = [...new Set(doc.buckets.map((b) => b.space))].sort();
    cell.lengthSumMm = doc.totals.length_sum_mm;
    cell.hatchAreaMm2 = doc.totals.hatch_area_sum_mm2;
  }
  const drops = loadJson(statsOut.replace(/\.json$/, '.drops.json'), null);
  if (drops) {
    cell.drops = Array.isArray(drops.drops) ? drops.drops.length : (drops.count ?? null);
    const kinds = {};
    for (const d of drops.drops ?? []) kinds[d.reason] = (kinds[d.reason] ?? 0) + 1;
    cell.dropKinds = kinds;
  }
  return cell;
}

/**
 * acad-ts (b'): the *other* converter. `dwg2dxf` writes a DXF from the same DWG;
 * the engine is then asked to read it (W2-06 found it could not, on synthetic
 * fixtures) and the group-code scanner reads the tables `dxfOut()` is suspected
 * of flattening (STYLE fonts + XDATA typeface, XREF path names, INSERT 66,
 * HATCH External). The converted DXF is deleted after the scan unless --keep:
 * it is several times the size of the DWG and carries drawing content.
 */
async function acadConvCell(f, workDir, args) {
  const out = join(workDir, `${f.id}.acadconv.dxf`);
  const cli = 'packages/acad-bridge/bin/acad-bridge.mjs';
  const cell = { path: 'acadconv', mode: 'acad-ts dwg2dxf' };
  const r = runTimed(process.execPath, [cli, 'dwg2dxf', f.abs, out], { timeout: args.timeout });
  cell.ok = r.ok;
  cell.timeMs = r.realMs;
  cell.peakRssBytes = r.peakRssBytes;
  if (!r.ok) {
    cell.error = r.timedOut ? `timeout after ${String(args.timeout)}s` : causeOf(r);
    return cell;
  }
  cell.outputBytes = existsSync(out) ? statSync(out).size : null;
  const drops = loadJson(out.replace(/\.dxf$/, '.drops.json'), null);
  if (drops) {
    cell.drops = Array.isArray(drops.drops) ? drops.drops.length : (drops.count ?? null);
    const kinds = {};
    for (const d of drops.drops ?? []) kinds[d.reason] = (kinds[d.reason] ?? 0) + 1;
    cell.dropKinds = kinds;
  }
  const statsOut = join(workDir, `${f.id}.acadconv.engine.json`);
  const e = runTimed('uv', ['run', '--project', 'engine', 'halo-engine', 'stats', out, '--out', statsOut], {
    timeout: args.timeout,
  });
  cell.engineReads = e.ok;
  cell.engineReadMs = e.realMs;
  if (!e.ok) cell.engineError = e.timedOut ? 'timeout' : causeOf(e);
  const doc = e.ok ? loadJson(statsOut, null) : null;
  if (doc) {
    cell.engineEntityCount = doc.totals.entity_count;
    cell.engineTextCount = doc.totals.text_count;
    cell.engineTextHash = doc.totals.text_hash;
  }
  try {
    const scan = await scanDxf(out);
    writeFileSync(join(workDir, `${f.id}.acadconv.scan.json`), JSON.stringify(scan, null, 1));
    cell.scan = {
      header: scan.header,
      styles: scan.styles,
      layerCount: scan.layers.length,
      layerNames: scan.layerNames,
      blocks: scan.blocks,
      xrefs: scan.xrefs,
      insert: scan.insert,
      hatch: scan.hatch,
      attrib: scan.attrib,
      text: scan.text,
      topLevel: scan.entities.topLevel,
      byType: scan.entities.byType,
      inBlockEntities: scan.inBlockEntities,
    };
  } catch (err) {
    cell.scanError = String(err?.message ?? err).slice(0, 200);
  }
  if (!args.keep && existsSync(out)) rmSync(out, { force: true });
  return cell;
}

/** ezdxf (c): read the DXF the browser's dxfOut() produced, plus a group-code scan. */
async function engineCell(f, workDir, args) {
  const dxf = join(workDir, `${f.id}.dxf`);
  if (!existsSync(dxf)) return { path: 'engine', ok: null, error: 'no dxfOut output yet (run --run-browser)' };
  const cell = { path: 'engine', mode: 'ezdxf stats on dxfOut DXF', dxfBytes: statSync(dxf).size };
  const out = join(workDir, `${f.id}.engine.json`);
  const r = runTimed('uv', ['run', '--project', 'engine', 'halo-engine', 'stats', dxf, '--out', out], {
    timeout: args.timeout,
  });
  cell.ok = r.ok;
  cell.timeMs = r.realMs;
  cell.peakRssBytes = r.peakRssBytes;
  if (!r.ok) cell.error = r.timedOut ? `timeout after ${String(args.timeout)}s` : causeOf(r);
  const doc = r.ok ? loadJson(out, null) : null;
  if (doc) {
    cell.entityCount = doc.totals.entity_count;
    cell.textCount = doc.totals.text_count;
    cell.textHash = doc.totals.text_hash;
    cell.countByType = doc.totals.count_by_type;
    cell.insertByBlock = Object.keys(doc.totals.insert_by_block ?? {}).length;
    cell.layers = [...new Set(doc.buckets.map((b) => b.layer))].length;
    cell.spacesSeen = [...new Set(doc.buckets.map((b) => b.space))].sort();
    cell.lengthSumMm = doc.totals.length_sum_mm;
    cell.hatchAreaMm2 = doc.totals.hatch_area_sum_mm2;
  }
  try {
    const scan = await scanDxf(dxf);
    writeFileSync(join(workDir, `${f.id}.scan.json`), JSON.stringify(scan, null, 1));
    cell.scan = {
      header: scan.header,
      styles: scan.styles,
      layerCount: scan.layers.length,
      layerNames: scan.layerNames,
      blocks: scan.blocks,
      xrefs: scan.xrefs,
      insert: scan.insert,
      hatch: scan.hatch,
      attrib: scan.attrib,
      text: scan.text,
      topLevel: scan.entities.topLevel,
      byType: scan.entities.byType,
      inBlockEntities: scan.inBlockEntities,
    };
  } catch (e) {
    cell.scanError = String(e?.message ?? e).slice(0, 200);
  }
  return cell;
}

async function runDirMode(args) {
  const files = enumerateSet(args.dir);
  mkdirSync(args.reports, { recursive: true });
  const workDir = join(args.reports, 'work');
  mkdirSync(workDir, { recursive: true });
  writeFileSync(
    join(args.reports, 'manifest.json'),
    JSON.stringify(Object.fromEntries(files.map((f) => [f.id, f.abs])), null, 1)
  );
  writeFileSync(join(args.reports, 'files.json'), JSON.stringify(files, null, 1));

  const sel = args.ids.length ? files.filter((f) => args.ids.includes(f.id)) : files;
  const cellsPath = join(args.reports, 'cells.json');
  const cells = args.fresh ? {} : loadJson(cellsPath, {});
  const started = Date.now();
  const overBudget = () => args.budgetMs > 0 && Date.now() - started > args.budgetMs;
  const flush = () => writeFileSync(cellsPath, JSON.stringify(cells, null, 1));

  if (args.runBrowser && args.paths.includes('dxfout')) {
    const have = readBrowserRows(join(args.reports, 'browser.jsonl'));
    const pending = sel.filter((f) => !have.has(f.id)).map((f) => f.id);
    if (pending.length) {
      process.stderr.write(`[bench] browser batch: ${String(pending.length)} pending\n`);
      const r = runTimed(
        process.execPath,
        [
          'scripts/bench-real.mjs',
          '--manifest', join(args.reports, 'manifest.json'),
          '--out', join(args.reports, 'browser.jsonl'),
          '--sink-dir', workDir,
          '--ids', pending.join(','),
          '--timeout', String(args.timeout),
          ...(args.budgetMs ? ['--budget-ms', String(args.budgetMs)] : []),
        ],
        { cwd: join(ROOT, 'spikes', 'mlightcad'), timeout: args.timeout * pending.length + 600 }
      );
      if (!r.ok) process.stderr.write(`[bench] browser batch ended: ${causeOf(r)}\n`);
    }
  }
  const browserRows = readBrowserRows(join(args.reports, 'browser.jsonl'));

  for (const f of sel) {
    if (args.paths.includes('acad')) {
      const key = `${f.id}|acad`;
      if (!cells[key] && !overBudget()) {
        cells[key] = acadCell(f, workDir, args);
        flush();
        process.stderr.write(
          `[bench] ${f.id} acad ${cells[key].ok ? 'ok' : 'FAIL'} ${String(cells[key].entityCount ?? '-')} ents\n`
        );
      }
    }
    if (args.paths.includes('acadconv')) {
      const key = `${f.id}|acadconv`;
      if (!cells[key] && !overBudget()) {
        cells[key] = await acadConvCell(f, workDir, args);
        flush();
        process.stderr.write(
          `[bench] ${f.id} acadconv ${cells[key].ok ? 'ok' : 'FAIL'} engine-reads=${String(cells[key].engineReads)}\n`
        );
      }
    }
    if (args.paths.includes('engine')) {
      const key = `${f.id}|engine`;
      if (!cells[key] && !overBudget()) {
        cells[key] = await engineCell(f, workDir, args);
        flush();
        process.stderr.write(
          `[bench] ${f.id} engine ${cells[key].ok === null ? 'n/a' : cells[key].ok ? 'ok' : 'FAIL'} ${String(cells[key].entityCount ?? '-')} ents\n`
        );
      }
    }
  }
  flush();

  // ------------------------------------------------------------------ report
  const rows = sel.map((f) => {
    const a = cells[`${f.id}|acad`] ?? {};
    const e = cells[`${f.id}|engine`] ?? {};
    const b = browserRows.get(f.id) ?? null;
    const bEnt = b?.survey?.ok ? b.survey.totalEntities : (b?.parse?.entityCount ?? null);
    return {
      id: f.id,
      file: f.name,
      dir: f.dir,
      bytes: f.bytes,
      versionMarker: a.versionMarker ?? versionMarker(f.abs),
      version: a.version ?? null,
      codePage: a.codePage ?? null,
      acad: {
        ok: a.ok ?? null,
        entityCount: a.entityCount ?? null,
        textCount: a.textCount ?? null,
        textHash: a.textHash ?? null,
        layers: a.layers ?? null,
        spaces: a.spacesSeen ?? null,
        timeMs: a.timeMs ?? null,
        peakRssBytes: a.peakRssBytes ?? null,
        drops: a.drops ?? null,
        error: a.error ?? a.infoError ?? null,
      },
      browser: b
        ? {
            ok: b.ok === true,
            entityCount: bEnt,
            modelSpace: b.parse?.entityCount ?? null,
            spaces: b.survey?.spaces ? Object.keys(b.survey.spaces).length : null,
            layers: b.survey?.layerNames?.length ?? b.parse?.layerCount ?? null,
            blocks: b.survey?.blockCount ?? b.parse?.blockCount ?? null,
            xrefBlocks: b.survey?.xrefBlocks?.length ?? null,
            lastOpenError: b.parse?.lastOpenError ?? null,
            parseMs: b.parse?.ms ? Math.round(b.parse.ms) : null,
            dxfOutMs: b.dxfOut?.ms ? Math.round(b.dxfOut.ms) : null,
            outputBytes: b.dxfOut?.bytes ?? null,
            peakRssBytes: b.peakRssBytes ?? null,
            error: b.error ?? null,
          }
        : { ok: null, error: 'not measured' },
      engine: {
        ok: e.ok ?? null,
        entityCount: e.entityCount ?? null,
        textCount: e.textCount ?? null,
        textHash: e.textHash ?? null,
        layers: e.layers ?? null,
        spaces: e.spacesSeen ?? null,
        timeMs: e.timeMs ?? null,
        peakRssBytes: e.peakRssBytes ?? null,
        dxfBytes: e.dxfBytes ?? null,
        error: e.error ?? null,
      },
      scan: e.scan ?? null,
      acadconv: cells[`${f.id}|acadconv`]
        ? {
            ok: cells[`${f.id}|acadconv`].ok,
            outputBytes: cells[`${f.id}|acadconv`].outputBytes ?? null,
            timeMs: cells[`${f.id}|acadconv`].timeMs ?? null,
            drops: cells[`${f.id}|acadconv`].drops ?? null,
            dropKinds: cells[`${f.id}|acadconv`].dropKinds ?? null,
            engineReads: cells[`${f.id}|acadconv`].engineReads ?? null,
            engineError: cells[`${f.id}|acadconv`].engineError ?? null,
            engineEntityCount: cells[`${f.id}|acadconv`].engineEntityCount ?? null,
            engineTextCount: cells[`${f.id}|acadconv`].engineTextCount ?? null,
            scan: cells[`${f.id}|acadconv`].scan ?? null,
          }
        : null,
      tier: TIER(e.entityCount ?? a.entityCount ?? null),
    };
  });

  const date = new Date().toISOString().slice(0, 10);
  const jsonPath = args.json ?? join(args.outDir, `results-real-${date}.json`);
  writeFileSync(
    jsonPath,
    JSON.stringify(
      {
        tool: 'tools/bench-open.mjs --dir',
        date,
        label: args.label,
        host: { platform: process.platform, arch: process.arch, node: process.version },
        set: { dir: basename(args.dir), files: files.length },
        note: 'aggregate numbers, file names and name statistics only -- no drawing content (W3-09 brief)',
        rows,
      },
      null,
      1
    )
  );

  if (args.summary) {
    const head = [
      '| id | file | folder | MB | ver | codepage | acad-ts | libredwg | ezdxf(dxfOut) | text a/e | layers a/e | tier | acad s | browser s | ezdxf s |',
      '|---|---|---|---:|---|---|---:|---:|---:|---|---|---|---:|---:|---:|',
    ];
    const body = rows.map((r) =>
      [
        r.id,
        r.file,
        r.dir,
        (r.bytes / 1048576).toFixed(2),
        r.version ?? r.versionMarker ?? '—',
        r.codePage ?? '—',
        r.acad.ok === false ? `FAIL` : (r.acad.entityCount ?? '—'),
        r.browser.ok === false ? `FAIL` : (r.browser.entityCount ?? '—'),
        r.engine.ok === false ? `FAIL` : (r.engine.entityCount ?? '—'),
        `${String(r.acad.textCount ?? '—')}/${String(r.engine.textCount ?? '—')}`,
        `${String(r.acad.layers ?? '—')}/${String(r.engine.layers ?? '—')}`,
        r.tier,
        secs(r.acad.timeMs),
        secs(r.browser.parseMs != null ? r.browser.parseMs + (r.browser.dxfOutMs ?? 0) : null),
        secs(r.engine.timeMs),
      ].join(' | ')
    );
    process.stdout.write([...head, ...body.map((b) => `| ${b} |`)].join('\n') + '\n');
  } else {
    const head = ['| id | file | path | entities | text | time | peak RSS | result |', '|---|---|---|---:|---:|---:|---:|---|'];
    const body = [];
    for (const r of rows) {
      for (const [k, c] of [['acad', r.acad], ['dxfout(browser)', r.browser], ['engine', r.engine]]) {
        body.push(
          [
            r.id,
            r.file,
            k,
            c.entityCount ?? '—',
            c.textCount ?? '—',
            secs(c.timeMs ?? (c.parseMs != null ? c.parseMs + (c.dxfOutMs ?? 0) : null)),
            c.peakRssBytes ? `${mb(c.peakRssBytes)} MB` : '—',
            c.ok === null ? `n/a: ${c.error ?? ''}` : c.ok ? 'ok' : `FAIL: ${String(c.error ?? '?').slice(0, 80)}`,
          ].join(' | ')
        );
      }
    }
    process.stdout.write([...head, ...body.map((b) => `| ${b} |`)].join('\n') + '\n');
  }
  process.stdout.write(`\nrows: ${String(rows.length)}\nresults: ${jsonPath}\ncells: ${cellsPath}\n`);
}

mkdirSync(args.outDir, { recursive: true });
mkdirSync(args.work, { recursive: true });

if (args.dir) {
  await runDirMode(args);
  process.exit(0);
}

const rows = [];

for (const file of args.files) {
  const abs = resolve(ROOT, file);
  if (!existsSync(abs)) {
    rows.push({ file, path: '-', ok: false, error: 'file not found' });
    continue;
  }
  const inputBytes = statSync(abs).size;
  const runs = inputBytes > args.largeBytes ? args.repeatLarge : args.repeat;

  for (const path of args.paths) {
    if (path === 'browser') continue; // batched below
    if (path === 'engine' && file.toLowerCase().endsWith('.dwg')) {
      // ADR-0002 §5: the engine reads DXF only. Not a failure, a scope line.
      rows.push({
        file: basename(file),
        inputBytes,
        path,
        mode: 'ezdxf stats',
        heap: 'default',
        runs: 0,
        ok: null,
        error: 'not applicable: the engine reads DXF only (ADR-0002 §5)',
      });
      continue;
    }
    for (const heap of path === 'engine' ? ['default'] : args.heaps) {
      const attempts = [];
      let last = null;
      for (let i = 0; i < runs; i++) {
        last =
          path === 'acad'
            ? runAcad(file, heap, args, args.work)
            : path === 'dxfout'
              ? runDxfOut(file, heap, args, args.work)
              : runEngine(file, args, args.work);
        attempts.push(last);
        if (!last.r.ok) break; // do not repeat a failure
      }
      const row = {
        file: basename(file),
        inputBytes,
        path,
        mode: last.mode,
        heap,
        runs: attempts.length,
        ok: last.r.ok,
        timeMsMedian: median(attempts.map((a) => a.r.realMs)),
        peakRssBytesMedian: median(attempts.map((a) => a.r.peakRssBytes)),
        outputBytes: last.r.ok && existsSync(last.out) ? statSync(last.out).size : null,
      };
      if (!last.r.ok) {
        row.error = last.r.timedOut ? `timeout after ${String(args.timeout)}s` : causeOf(last.r);
        if (last.detail?.error) row.error = last.detail.error.split('\n')[0].slice(0, 300);
      }
      if (last.detail) {
        row.detail = {
          heapLimitBytes: last.detail.heapLimitBytes,
          parseMs: last.detail.parseMs,
          dxfOutMs: last.detail.dxfOutMs,
          entityCount: last.detail.entityCount,
        };
      }
      // fidelity
      if (args.fidelity && last.r.ok) {
        if (last.producesStats) {
          try {
            row.fidelity = fidelityOf(JSON.parse(readFileSync(last.out, 'utf8')), file, args);
            row.fidelitySource = path === 'engine' ? 'ezdxf (self)' : 'acad-ts stats';
          } catch (e) {
            row.fidelity = { error: String(e.message ?? e).slice(0, 120) };
          }
        } else if (last.producesDxf) {
          const es = engineStats(last.out, `${last.out}.stats.json`, args.timeout);
          row.engineReadMs = es.r.realMs;
          row.engineReadRssBytes = es.r.peakRssBytes;
          row.fidelity = es.doc ? fidelityOf(es.doc, file, args) : { error: es.error };
          row.fidelitySource = 'ezdxf on output DXF';
        }
        if (last.selfView) {
          try {
            row.parserSelfView = fidelityOf(JSON.parse(readFileSync(last.selfView, 'utf8')), file, args);
          } catch {
            /* ignore: the self-view is a secondary signal */
          }
        }
      }
      rows.push(row);
      process.stderr.write(
        `[bench] ${row.file} ${path}/${heap} ${row.ok ? 'ok' : 'FAIL'} ${secs(row.timeMsMedian)}s ${mb(row.peakRssBytesMedian)}MB\n`
      );
    }
  }
}

if (args.paths.includes('browser')) {
  const browserRows = runBrowserAll(args.files, args, args.work);
  for (const br of browserRows) {
    const src = args.files.find((f) => basename(f) === br.file) ?? br.file;
    const row = {
      file: br.file,
      inputBytes: br.inputBytes ?? null,
      path: 'browser',
      mode: args.browserRender ? 'viewer render' : 'parse + dxfOut',
      heap: 'chromium default',
      runs: br.runs ?? 1,
      ok: br.ok === true,
      timeMsMedian:
        br.medianTotalMs ??
        (br.render
          ? Math.round(br.render.ms)
          : br.parse
            ? Math.round((br.parse.ms ?? 0) + (br.dxfOut?.ms ?? 0))
            : null),
      peakRssBytesMedian: br.medianPeakRssBytes ?? br.peakRssBytes ?? null,
      detail: {
        fetchMs: br.fetch?.ms,
        parseMs: br.parse ? Math.round(br.parse.ms) : undefined,
        dxfOutMs: br.dxfOut ? Math.round(br.dxfOut.ms) : undefined,
        entityCount: br.parse?.entityCount ?? br.render?.entityCount,
        baselineRssBytes: br.baselineRssBytes,
        parseRssBytes: br.parse?.rss?.totalRssBytes,
        largestProcRssBytes: br.peakLargestProcRssBytes,
        outputBytes: br.dxfOut?.bytes,
      },
      error: br.error ?? br.parse?.error ?? br.render?.error,
    };
    if (args.fidelity && br.dxfOut?.ok && br.dxfOut.file && existsSync(br.dxfOut.file)) {
      const es = engineStats(br.dxfOut.file, `${br.dxfOut.file}.stats.json`, args.timeout);
      row.engineReadMs = es.r.realMs;
      row.fidelity = es.doc ? fidelityOf(es.doc, src, args) : { error: es.error };
      row.fidelitySource = 'ezdxf on output DXF';
    }
    rows.push(row);
    process.stderr.write(
      `[bench] ${row.file} browser ${row.ok ? 'ok' : 'FAIL'} ${secs(row.timeMsMedian)}s ${mb(row.peakRssBytesMedian)}MB\n`
    );
  }
}

// --------------------------------------------------------------------------
// report
// --------------------------------------------------------------------------
const date = new Date().toISOString().slice(0, 10);
const result = {
  tool: 'tools/bench-open.mjs',
  date,
  label: args.label,
  host: { platform: process.platform, arch: process.arch, node: process.version },
  args: { paths: args.paths, files: args.files, heaps: args.heaps, repeat: args.repeat, repeatLarge: args.repeatLarge },
  rows,
};
const jsonPath = args.json ?? join(args.outDir, `results-${date}.json`);
// One file per day, appending each invocation as a `runs[]` entry, so the
// document keeps the whole matrix instead of only the last command.
let previous = [];
if (existsSync(jsonPath)) {
  try {
    const prev = JSON.parse(readFileSync(jsonPath, 'utf8'));
    previous = prev.runs ?? [];
  } catch {
    /* unreadable file: start over */
  }
}
writeFileSync(
  jsonPath,
  JSON.stringify({ tool: result.tool, date, host: result.host, runs: [...previous, result] }, null, 2)
);

const head = [
  '| file | input | path | mode | heap | runs | time (median) | peak RSS | result | fidelity vs truth | parser self-view |',
  '|---|---:|---|---|---|---:|---:|---:|---|---|---|',
];
const body = rows.map((r) =>
  [
    r.file,
    `${mb(r.inputBytes)} MB`,
    r.path,
    r.mode ?? '',
    r.heap ?? '',
    String(r.runs ?? ''),
    r.ok ? `${secs(r.timeMsMedian)} s` : '—',
    r.peakRssBytesMedian ? `${mb(r.peakRssBytesMedian)} MB` : '—',
    r.ok === null
      ? `n/a: ${r.error ?? ''}`
      : r.ok
        ? r.outputBytes || r.detail?.outputBytes
          ? `${mb(r.outputBytes ?? r.detail.outputBytes)} MB out`
          : 'ok'
        : `FAIL: ${r.error ?? '?'}`,
    fidelityCell(r.fidelity),
    r.parserSelfView ? fidelityCell(r.parserSelfView) : '—',
  ].join(' | ')
);
process.stdout.write([...head, ...body.map((b) => `| ${b} |`)].join('\n') + '\n');
process.stdout.write(`\nresults: ${jsonPath}\n`);

if (!args.keep) {
  for (const f of args.files) {
    for (const suffix of ['.acad.dxf', '.dxfout.dxf']) {
      const p = join(args.work, stem(f) + suffix);
      if (existsSync(p)) rmSync(p, { force: true });
    }
  }
}
