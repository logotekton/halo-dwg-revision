/**
 * W2-06 — path (c): @mlightcad/data-model in headless Node (CommonJS), the
 * ADR-0002 tier-2 converter's writer half.
 *
 * Reads one drawing and writes `AcDbDatabase.dxfOut()` to disk, reporting
 * timings, byte counts and the entity/handle set so the caller can check both
 * speed and fidelity. Run under `/usr/bin/time -l` for peak RSS; this script
 * additionally reports V8's own heap limit and its self-observed RSS peak so a
 * heap-cap OOM can be told apart from an RSS ceiling.
 *
 *   node scripts/bench-dxfout.cjs --in <f.dxf|f.dwg> --out <f.dxf> \
 *        [--version AC1032] [--precision 6] [--report r.json] [--handles]
 *
 * DWG input is attempted honestly and is expected to fail: data-model's DWG
 * converter forces `useWorker: true` and there is no `Worker` global in Node
 * (see the report line `dwgInNode`). CJS is mandatory -- the ESM entry uses
 * extensionless directory imports (spike fact C.11).
 *
 * GPL note (CLAUDE.md rule 3): @mlightcad/libredwg-converter is required only
 * inside this spike file, never from packages/ or apps/.
 */
const fs = require('node:fs');
const v8 = require('node:v8');
const dm = require('@mlightcad/data-model');

function parseArgs(argv) {
  const out = { precision: 6, version: 'AC1032', handles: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--in') out.in = argv[++i];
    else if (a === '--out') out.out = argv[++i];
    else if (a === '--report') out.report = argv[++i];
    else if (a === '--version') out.version = argv[++i];
    else if (a === '--precision') out.precision = Number(argv[++i]);
    else if (a === '--handles') out.handles = true;
    else throw new Error(`unknown argument: ${a}`);
  }
  if (!out.in) throw new Error('--in is required');
  return out;
}

const errText = (e) => String((e && (e.stack || e.message)) || e).slice(0, 600);
const toArrayBuffer = (buf) => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);

/** Sample our own RSS while the event loop is free, as a sanity check on time -l. */
function rssSampler() {
  let peak = process.memoryUsage.rss();
  const t = setInterval(() => {
    const rss = process.memoryUsage.rss();
    if (rss > peak) peak = rss;
  }, 100);
  t.unref();
  return {
    stop() {
      clearInterval(t);
      const rss = process.memoryUsage.rss();
      return Math.max(peak, rss);
    },
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const sampler = rssSampler();
  const report = {
    tool: 'bench-dxfout.cjs',
    node: process.version,
    // @mlightcad/data-model's package.json is not in its `exports` map, so the
    // version cannot be require()d by subpath (spike fact C.11).
    heapLimitBytes: v8.getHeapStatistics().heap_size_limit,
    input: args.in,
    inputBytes: fs.statSync(args.in).size,
    fileType: args.in.toLowerCase().endsWith('.dwg') ? 'dwg' : 'dxf',
    ok: false,
  };

  if (report.fileType === 'dwg') {
    // Register the DWG converter so the failure mode is the real one, not a
    // "no converter registered" error.
    try {
      const { AcDbLibreDwgConverter } = require('@mlightcad/libredwg-converter');
      dm.AcDbDatabaseConverterManager.instance.register(
        dm.AcDbFileType.DWG,
        new AcDbLibreDwgConverter({ useWorker: true })
      );
      report.dwgConverterRegistered = true;
    } catch (e) {
      report.dwgConverterRegistered = false;
      report.dwgConverterError = errText(e);
    }
  }

  const tRead0 = Date.now();
  const bytes = fs.readFileSync(args.in);
  report.readFileMs = Date.now() - tRead0;

  const db = new dm.AcDbDatabase();
  const tParse0 = Date.now();
  try {
    await db.read(
      toArrayBuffer(bytes),
      { readOnly: false },
      report.fileType === 'dwg' ? dm.AcDbFileType.DWG : dm.AcDbFileType.DXF
    );
    report.parseMs = Date.now() - tParse0;
  } catch (e) {
    report.parseMs = Date.now() - tParse0;
    report.error = errText(e);
    report.dwgInNode = report.fileType === 'dwg' ? 'unsupported: no Worker global in Node' : undefined;
    report.peakRssBytes = sampler.stop();
    finish(args, report);
    return;
  }

  report.version = db.version;
  const before = [];
  let count = 0;
  const byType = {};
  for (const e of db.tables.blockTable.modelSpace.newIterator()) {
    byType[e.dxfTypeName] = (byType[e.dxfTypeName] || 0) + 1;
    count++;
    if (args.handles) before.push(e.objectId);
  }
  report.entityCount = count;
  report.byType = byType;
  report.layerCount = [...db.tables.layerTable.newIterator()].length;
  report.blockCount = [...db.tables.blockTable.newIterator()].length;

  const tOut0 = Date.now();
  const dxf = db.dxfOut(args.out || 'out.dxf', args.precision, args.version);
  report.dxfOutMs = Date.now() - tOut0;
  report.outputBytes = typeof dxf === 'string' ? Buffer.byteLength(dxf, 'utf8') : dxf.byteLength;

  if (args.out) {
    const tW0 = Date.now();
    fs.writeFileSync(args.out, dxf);
    report.writeMs = Date.now() - tW0;
  }
  if (args.handles) {
    const db2 = new dm.AcDbDatabase();
    await db2.read(
      typeof dxf === 'string' ? toArrayBuffer(Buffer.from(dxf, 'utf8')) : toArrayBuffer(Buffer.from(dxf)),
      { readOnly: true },
      dm.AcDbFileType.DXF
    );
    const after = [...db2.tables.blockTable.modelSpace.newIterator()].map((e) => e.objectId);
    report.handlesPreserved =
      JSON.stringify([...before].sort()) === JSON.stringify([...after].sort());
    report.reopenEntityCount = after.length;
  }

  report.ok = true;
  report.peakRssBytes = sampler.stop();
  finish(args, report);
}

function finish(args, report) {
  const json = JSON.stringify(report, null, 2);
  if (args.report) fs.writeFileSync(args.report, json);
  process.stdout.write(json + '\n');
  process.exitCode = report.ok ? 0 : 1;
}

main().catch((e) => {
  process.stderr.write(`bench-dxfout failed: ${errText(e)}\n`);
  process.exit(2);
});
