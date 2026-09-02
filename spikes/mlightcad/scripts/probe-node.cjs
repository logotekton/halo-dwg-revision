/**
 * W1-04 spike — headless Node probe (API fact 11).
 *
 * Loads @mlightcad/data-model through its CommonJS build. The ESM entry
 * (`lib/index.js`) uses extensionless directory imports and Node's ESM resolver
 * rejects it with ERR_UNSUPPORTED_DIR_IMPORT, so `require()` is the only
 * headless route without a bundler.
 *
 * Also re-runs the dxfOut() round trip outside the browser so ADR-0002 tier 2
 * has a Node-side number as well.
 *
 * Run: npm run probe:node
 */
const fs = require('node:fs');
const path = require('node:path');
const dm = require('@mlightcad/data-model');

const FIX = path.resolve(__dirname, '..', 'fixtures');
const OUT = path.resolve(__dirname, '..', 'out');

const toBuf = (str) => new TextEncoder().encode(str).buffer;

async function openDxf(text) {
  const db = new dm.AcDbDatabase();
  await db.read(toBuf(text), { readOnly: false }, dm.AcDbFileType.DXF);
  return db;
}

function rows(db) {
  const out = [];
  for (const e of db.tables.blockTable.modelSpace.newIterator()) {
    out.push({
      handle: e.objectId,
      // Two stable discriminators. `dxfTypeName` is the DXF record name;
      // `type` returns `this.constructor.typeName` (a static field), so it
      // survives minification even though the JSDoc claims it derives from
      // the constructor name. Note DIMENSION subclasses report the subclass
      // in `type` (RotatedDimension) but DIMENSION in `dxfTypeName`.
      dxfTypeName: e.dxfTypeName,
      typeGetter: e.type,
      ctorName: e.constructor.name,
      layer: e.layer,
      owner: e.ownerId,
    });
  }
  return out;
}

const byType = (list) =>
  list.reduce((m, r) => ((m[r.dxfTypeName] = (m[r.dxfTypeName] ?? 0) + 1), m), {});

(async () => {
  const report = {
    node: process.version,
    dataModel: JSON.parse(
      fs.readFileSync(
        path.resolve(__dirname, '..', 'node_modules', '@mlightcad', 'data-model', 'package.json'),
        'utf8'
      )
    ).version,
    note: "package.json is not in @mlightcad/data-model's `exports` map, so it cannot be require()d by subpath",
  };

  // --- ESM entry is unusable in Node
  try {
    await import('@mlightcad/data-model');
    report.esmImport = 'works';
  } catch (e) {
    report.esmImport = { failed: e.code ?? String(e).slice(0, 120) };
  }

  const src = fs.readFileSync(path.join(FIX, 'F-spike-r2018.dxf'), 'utf8');
  const t0 = Date.now();
  const db = await openDxf(src);
  report.openMs = Date.now() - t0;
  report.version = db.version;
  report.lastOpenError = db.lastOpenError;

  report.layers = [...db.tables.layerTable.newIterator()].map((l) => ({ name: l.name, handle: l.objectId }));
  report.blocks = [...db.tables.blockTable.newIterator()].map((b) => ({
    name: b.name,
    handle: b.objectId,
    count: b.newIterator().count,
  }));
  const before = rows(db);
  report.modelSpace = { count: before.length, byType: byType(before), rows: before };

  // --- dxfOut round trip
  const out = db.dxfOut('roundtrip.dxf', 6, 'AC1032');
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'roundtrip-node.dxf'), out);
  const db2 = await openDxf(out);
  const after = rows(db2);
  const h = (l) => l.map((r) => r.handle).sort();
  report.roundTrip = {
    asciiBytes: Buffer.byteLength(out, 'utf8'),
    acadver: /\$ACADVER\r?\n\s*1\r?\n(\S+)/.exec(out)?.[1],
    count: after.length,
    byType: byType(after),
    handlesPreserved: JSON.stringify(h(before)) === JSON.stringify(h(after)),
    layers: [...db2.tables.layerTable.newIterator()].map((l) => `${l.name}#${l.objectId}`),
    blocks: [...db2.tables.blockTable.newIterator()].map((b) => `${b.name}#${b.objectId}`),
  };

  // --- CP949 R2000 variant, read as raw bytes (no manual decoding by the caller)
  const cp949 = fs.readFileSync(path.join(FIX, 'F-spike-r2000-cp949.dxf'));
  const dbK = new dm.AcDbDatabase();
  await dbK.read(cp949.buffer.slice(cp949.byteOffset, cp949.byteOffset + cp949.byteLength), { readOnly: true }, dm.AcDbFileType.DXF);
  report.cp949 = {
    version: dbK.version,
    layers: [...dbK.tables.layerTable.newIterator()].map((l) => l.name),
    text: [...dbK.tables.blockTable.modelSpace.newIterator()]
      .filter((e) => e.dxfTypeName === 'TEXT' || e.dxfTypeName === 'MTEXT')
      .map((e) => e.textString ?? e.contents),
  };

  fs.writeFileSync(path.join(OUT, 'probe-node.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ ...report, modelSpace: { ...report.modelSpace, rows: '<omitted>' } }, null, 2));
})().catch((e) => {
  console.error('PROBE FAILED', e);
  process.exit(1);
});
