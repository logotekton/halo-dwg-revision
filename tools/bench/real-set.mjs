/**
 * W3-09 — enumeration of a real drawing folder (`--dir` mode of bench-open.mjs).
 *
 * The set the user handed over lives outside the repo and is read-only
 * (`CLAUDE.md` rule 1 and the W3-09 brief: never write into it, never commit its
 * content). Everything downstream addresses a drawing by a **stable id**
 * derived from the sorted relative path, because the real names carry spaces,
 * `#` and Hangul and travel through URLs, sink filenames and shell arguments.
 *
 * Ids are stable as long as the set is: `S001` is the first path in NFC
 * code-point order, and a file added later shifts the ids after it — the
 * manifest records the mapping, so a shifted id is always detectable by
 * comparing `bytes`.
 */
import { closeSync, openSync, readSync, readdirSync, statSync } from 'node:fs';
import { basename, extname, join, relative, sep } from 'node:path';

/** `.bak` is AutoCAD's previous save, not a drawing to measure (brief default). */
const DRAWING = /\.(dwg|dxf)$/i;

/** Recursive listing, skipping dot files and AutoCAD scratch. */
function walk(dir, out = []) {
  for (const name of readdirSync(dir).sort()) {
    if (name.startsWith('.')) continue;
    const abs = join(dir, name);
    let st;
    try {
      st = statSync(abs);
    } catch {
      continue;
    }
    if (st.isDirectory()) walk(abs, out);
    else if (DRAWING.test(name)) out.push({ abs, bytes: st.size });
  }
  return out;
}

/** First bytes of a DWG are its version marker (`AC1024` = R2010). */
export function versionMarker(abs) {
  try {
    const fd = openSync(abs, 'r');
    const buf = Buffer.alloc(6);
    readSync(fd, buf, 0, 6, 0);
    closeSync(fd);
    return buf.toString('latin1');
  } catch {
    return null;
  }
}

/**
 * @param {string} dir root of the drawing set
 * @returns {{id:string, abs:string, rel:string, name:string, dir:string, ext:string, bytes:number}[]}
 */
export function enumerateSet(dir) {
  const files = walk(dir);
  files.sort((a, b) => (a.abs.normalize('NFC') < b.abs.normalize('NFC') ? -1 : 1));
  return files.map((f, i) => {
    const rel = relative(dir, f.abs);
    return {
      id: `S${String(i + 1).padStart(3, '0')}`,
      abs: f.abs,
      rel,
      name: basename(f.abs),
      dir: rel.split(sep).slice(0, -1).join('/') || '.',
      ext: extname(f.abs).slice(1).toLowerCase(),
      bytes: f.bytes,
    };
  });
}
