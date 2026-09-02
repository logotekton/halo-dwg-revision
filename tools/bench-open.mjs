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

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const ALL_PATHS = ['acad', 'dxfout', 'browser', 'engine'];

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
    else if (k === '--help' || k === '-h') a.help = true;
    else throw new Error(`unknown argument: ${k}`);
  }
  if (a.help) return a;
  if (a.files.length === 0) throw new Error('--files is required');
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

function engineStats(dxfPath, outJson, timeout) {
  const r = runTimed('uv', ['run', '--project', 'engine', 'halo-engine', 'stats', dxfPath, '--out', outJson], {
    timeout,
  });
  if (!r.ok) {
    return { r, doc: null, error: (r.stderr.trim().split('\n').pop() ?? `exit ${String(r.status)}`).slice(0, 200) };
  }
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
  return { r, out, mode: isDwg ? 'dwg2dxf' : 'stats', producesDxf: isDwg, producesStats: !isDwg };
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

/** The browser path is batched: one driver run covers every file. */
function runBrowserBatch(files, args, work) {
  const names = files.map((f) => basename(f));
  const report = join(work, 'browser.report.json');
  const spike = join(ROOT, 'spikes', 'mlightcad');
  const argv = [
    'scripts/bench-browser.mjs',
    '--files',
    names.join(','),
    '--report',
    report,
    '--timeout',
    String(args.timeout),
  ];
  if (!args.browserRender) argv.push('--dxfout');
  else argv.push('--render');
  const r = runTimed(process.execPath, argv, { cwd: spike, timeout: args.timeout * (files.length + 1) });
  let rows = [];
  try {
    rows = JSON.parse(readFileSync(report, 'utf8')).rows;
  } catch {
    rows = files.map((f) => ({
      file: basename(f),
      ok: false,
      error: (r.stderr.trim().split('\n').pop() ?? 'driver failed').slice(0, 300),
    }));
  }
  return { r, rows, sinkDir: join(spike, 'out', 'bench') };
}

// --------------------------------------------------------------------------
// main
// --------------------------------------------------------------------------
const args = parseArgs(process.argv.slice(2));
if (args.help) {
  process.stdout.write(USAGE);
  process.exit(0);
}
mkdirSync(args.outDir, { recursive: true });
mkdirSync(args.work, { recursive: true });

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
        const tail = (last.r.stderr || last.r.stdout || '').trim().split('\n').filter(Boolean);
        row.error = last.r.timedOut
          ? `timeout after ${String(args.timeout)}s`
          : (tail.find((l) => /error|Error|FATAL|failed|heap/.test(l)) ?? tail.pop() ?? `exit ${String(last.r.status)}`).slice(0, 300);
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
      }
      rows.push(row);
      process.stderr.write(
        `[bench] ${row.file} ${path}/${heap} ${row.ok ? 'ok' : 'FAIL'} ${secs(row.timeMsMedian)}s ${mb(row.peakRssBytesMedian)}MB\n`
      );
    }
  }
}

if (args.paths.includes('browser')) {
  const batch = runBrowserBatch(args.files, args, args.work);
  for (const br of batch.rows) {
    const src = args.files.find((f) => basename(f) === br.file) ?? br.file;
    const row = {
      file: br.file,
      inputBytes: br.inputBytes ?? null,
      path: 'browser',
      mode: args.browserRender ? 'viewer render' : 'parse + dxfOut',
      heap: 'chromium default',
      runs: 1,
      ok: br.ok === true,
      timeMsMedian: br.render
        ? Math.round(br.render.ms)
        : br.parse
          ? Math.round((br.parse.ms ?? 0) + (br.dxfOut?.ms ?? 0))
          : null,
      peakRssBytesMedian: br.peakRssBytes ?? null,
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
  '| file | input | path | mode | heap | runs | time (median) | peak RSS | out | fidelity vs truth |',
  '|---|---:|---|---|---|---:|---:|---:|---:|---|',
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
    r.ok ? (r.outputBytes || r.detail?.outputBytes ? `${mb(r.outputBytes ?? r.detail.outputBytes)} MB` : 'ok') : `FAIL: ${r.error ?? '?'}`,
    fidelityCell(r.fidelity),
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
