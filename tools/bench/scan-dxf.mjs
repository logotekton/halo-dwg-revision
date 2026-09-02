#!/usr/bin/env node
/**
 * W3-09 — group-code level scan of a DXF, for the facts the three parsers'
 * `LayerStatsDocument` does not carry: text styles (SHX/TTF font file names),
 * XREF block records and their stored paths, the two group codes ADR-0002's
 * amendment says `dxfOut()` drops (INSERT `66`, HATCH boundary `92` External
 * bit), and how much of the text is Hangul / mojibake.
 *
 *   node tools/bench/scan-dxf.mjs <file.dxf> --out <scan.json>
 *
 * **No drawing content leaves this script.** Text values are counted, classified
 * and hashed; they are never stored in the output. Layer, block, style and font
 * *names* are kept — the brief allows name statistics, not bodies.
 *
 * Streams the file line by line (a converted 20 MB DWG can be a 300 MB DXF), so
 * peak memory is the tables, not the drawing.
 */
import { createReadStream, mkdirSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { createInterface } from 'node:readline';

const HANGUL = /[가-힣ᄀ-ᇿ㄰-㆏]/;
/**
 * CP949/UTF-8 bytes decoded as Latin-1 come out as runs of U+00A1..U+00FF, and a
 * failed decode leaves U+FFFD. A single accented letter is ordinary text, so the
 * run has to be at least two characters long before it counts as mojibake.
 */
const MOJIBAKE = /\uFFFD|[\u00A1-\u00FF]{2,}/;

const HEADER_VARS = new Set([
  '$ACADVER',
  '$DWGCODEPAGE',
  '$INSUNITS',
  '$MEASUREMENT',
  '$LTSCALE',
  '$DIMSCALE',
  '$HANDSEED',
]);

/** Entities that belong to an owner and are not counted as top level. */
const OWNED = new Set(['ATTRIB', 'SEQEND', 'VERTEX']);

export async function scanDxf(file) {
  const out = {
    file,
    header: {},
    styles: [],
    layers: [],
    linetypes: 0,
    dimstyles: 0,
    blocks: { total: 0, xref: 0, xrefOverlay: 0, anonymous: 0 },
    xrefs: [],
    entities: { topLevel: 0, byType: {}, byLayerTop: 0 },
    inBlockEntities: 0,
    text: { count: 0, hangul: 0, mojibake: 0, empty: 0, inBlock: 0, hash: null },
    insert: { total: 0, withCode66: 0 },
    hatch: { total: 0, boundaryPaths: 0, external: 0, polyline: 0, derived: 0 },
    attrib: { total: 0 },
    layerNames: [],
    layerUse: {},
    truncated: false,
  };

  const rl = createInterface({ input: createReadStream(file, { encoding: 'utf8' }), crlfDelay: Infinity });
  let code = null;
  let section = null;
  let tableKind = null;
  let ctx = null; // current record being filled
  let where = 'none'; // 'tables' | 'blocks' | 'entities'
  let blockDepth = 0;
  const textHash = createHash('sha1');
  const layerSet = new Set();
  const layerUse = new Map();

  const flushCtx = () => {
    if (!ctx) return;
    if (ctx.kind === 'STYLE') {
      out.styles.push({
        name: ctx.n2 ?? '',
        font: ctx.n3 ?? '',
        bigFont: ctx.n4 ?? '',
        typeface: ctx.typeface ?? '',
        flags: ctx.n70 ?? 0,
        height: ctx.n40 ?? 0,
      });
    } else if (ctx.kind === 'LAYER') {
      out.layers.push({ name: ctx.n2 ?? '', color: ctx.n62 ?? 0, linetype: ctx.n6 ?? '' });
    } else if (ctx.kind === 'BLOCK') {
      out.blocks.total++;
      const flags = ctx.n70 ?? 0;
      const name = ctx.n2 ?? '';
      if (flags & 1) out.blocks.anonymous++;
      if (flags & 4) {
        out.blocks.xref++;
        out.xrefs.push({ block: name, path: ctx.n1 ?? '', overlay: Boolean(flags & 8) });
        if (flags & 8) out.blocks.xrefOverlay++;
      }
    } else if (ctx.kind === 'ENTITY') {
      const t = ctx.type;
      if (!OWNED.has(t)) {
        out.entities.topLevel++;
        out.entities.byType[t] = (out.entities.byType[t] ?? 0) + 1;
        const l = ctx.n8 ?? '0';
        layerUse.set(l, (layerUse.get(l) ?? 0) + 1);
      }
      if (t === 'INSERT') {
        out.insert.total++;
        if (ctx.n66 === 1) out.insert.withCode66++;
      }
      if (t === 'ATTRIB') out.attrib.total++;
      if (t === 'HATCH') out.hatch.total++;
    } else if (ctx.kind === 'BLOCKENT' && ctx.type === 'HATCH') {
      out.hatch.total++;
    }
    ctx = null;
  };

  for await (const raw of rl) {
    if (code === null) {
      const c = Number(raw.trim());
      if (!Number.isFinite(c)) continue;
      code = c;
      continue;
    }
    const value = raw;
    const c = code;
    code = null;

    if (c === 0) {
      const v = value.trim().toUpperCase();
      if (v === 'SECTION') {
        flushCtx();
        ctx = { kind: 'SECTION' };
        continue;
      }
      if (v === 'ENDSEC') {
        flushCtx();
        section = null;
        where = 'none';
        tableKind = null;
        continue;
      }
      if (v === 'TABLE') {
        flushCtx();
        ctx = { kind: 'TABLE' };
        continue;
      }
      if (v === 'ENDTAB') {
        flushCtx();
        tableKind = null;
        continue;
      }
      if (v === 'ENDBLK') {
        flushCtx();
        blockDepth = 0;
        continue;
      }
      if (v === 'EOF') {
        flushCtx();
        break;
      }
      flushCtx();
      if (where === 'tables') {
        if (v === 'STYLE') ctx = { kind: 'STYLE' };
        else if (v === 'LAYER') ctx = { kind: 'LAYER' };
        else {
          if (v === 'LTYPE') out.linetypes++;
          if (v === 'DIMSTYLE') out.dimstyles++;
          ctx = { kind: 'OTHER' };
        }
      } else if (where === 'blocks') {
        if (v === 'BLOCK') {
          blockDepth = 1;
          ctx = { kind: 'BLOCK' };
        } else {
          out.inBlockEntities++;
          ctx = { kind: 'BLOCKENT', type: v };
        }
      } else if (where === 'entities') {
        ctx = { kind: 'ENTITY', type: v };
      } else {
        ctx = { kind: 'OTHER', type: v };
      }
      continue;
    }

    if (ctx?.kind === 'SECTION' && c === 2) {
      section = value.trim().toUpperCase();
      where = section === 'TABLES' ? 'tables' : section === 'BLOCKS' ? 'blocks' : section === 'ENTITIES' ? 'entities' : 'none';
      ctx = null;
      continue;
    }
    if (ctx?.kind === 'TABLE' && c === 2) {
      tableKind = value.trim().toUpperCase();
      ctx = null;
      continue;
    }

    // HEADER variables: `9 $NAME` then the value on the next group.
    if (section === 'HEADER') {
      if (c === 9) {
        ctx = { kind: 'HDR', name: value.trim().toUpperCase() };
        continue;
      }
      if (ctx?.kind === 'HDR' && HEADER_VARS.has(ctx.name) && out.header[ctx.name] === undefined) {
        out.header[ctx.name] = value.trim();
      }
      continue;
    }

    if (!ctx) continue;

    // Text bodies are classified and hashed, never stored.
    const isTextCarrier =
      (ctx.kind === 'ENTITY' || ctx.kind === 'BLOCKENT') &&
      (ctx.type === 'TEXT' || ctx.type === 'MTEXT' || ctx.type === 'ATTRIB' || ctx.type === 'ATTDEF');
    if (isTextCarrier && (c === 1 || (c === 3 && ctx.type === 'MTEXT'))) {
      const s = value;
      if (c === 1) {
        if (ctx.kind === 'BLOCKENT') out.text.inBlock++;
        else out.text.count++;
        if (!s.trim()) out.text.empty++;
        if (HANGUL.test(s)) out.text.hangul++;
        else if (MOJIBAKE.test(s)) out.text.mojibake++;
      }
      textHash.update(s.normalize('NFC'));
      textHash.update('\n');
      continue;
    }

    if (c === 1001 && ctx.kind === 'STYLE') {
      ctx.xdataApp = value.trim();
      continue;
    }
    if (c === 1000 && ctx.kind === 'STYLE' && ctx.xdataApp === 'ACAD' && ctx.typeface === undefined) {
      ctx.typeface = value;
      continue;
    }
    if (c === 1 && ctx.kind === 'BLOCK') ctx.n1 = value;
    else if (c === 2) ctx.n2 = value;
    else if (c === 3) ctx.n3 = value;
    else if (c === 4) ctx.n4 = value;
    else if (c === 6) ctx.n6 = value;
    else if (c === 8) ctx.n8 = value;
    else if (c === 40 && ctx.kind === 'STYLE') ctx.n40 = Number(value);
    else if (c === 62) ctx.n62 = Number(value);
    else if (c === 66) ctx.n66 = Number(value.trim());
    else if (c === 70) ctx.n70 = Number(value.trim());
    else if (c === 92 && ctx.type === 'HATCH') {
      const flags = Number(value.trim());
      out.hatch.boundaryPaths++;
      if (flags & 1) out.hatch.external++;
      if (flags & 2) out.hatch.polyline++;
      if (flags & 4) out.hatch.derived++;
    }
    if (c === 8 && ctx.kind === 'ENTITY') layerSet.add(value);
  }
  rl.close();

  out.text.hash = textHash.digest('hex').slice(0, 16);
  out.layerNames = out.layers.map((l) => l.name).sort();
  out.entities.byLayerTop = layerUse.size;
  out.layerUse = Object.fromEntries([...layerUse.entries()].sort((a, b) => b[1] - a[1]));
  out.entities.byType = Object.fromEntries(Object.entries(out.entities.byType).sort((a, b) => b[1] - a[1]));
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const file = process.argv[2];
  const outIdx = process.argv.indexOf('--out');
  if (!file) {
    process.stderr.write('usage: node tools/bench/scan-dxf.mjs <file.dxf> [--out scan.json]\n');
    process.exit(1);
  }
  const res = await scanDxf(resolve(file));
  const json = JSON.stringify(res, null, 2);
  if (outIdx > 0) {
    const p = resolve(process.argv[outIdx + 1]);
    mkdirSync(dirname(p), { recursive: true });
    writeFileSync(p, json);
    process.stdout.write(`${p}\n`);
  } else {
    process.stdout.write(`${json}\n`);
  }
}
