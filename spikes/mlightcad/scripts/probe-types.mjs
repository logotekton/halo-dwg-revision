/**
 * W1-04 spike — static type-declaration digest.
 *
 * Condenses selected `.d.ts` files from node_modules/@mlightcad/* into a flat
 * list of public members so the API document can quote exact identifiers.
 *
 * Usage:  node scripts/probe-types.mjs <path-under-node_modules/@mlightcad> [...]
 * Example: node scripts/probe-types.mjs cad-simple-viewer/lib/view/AcTrView2d.d.ts
 */
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'node_modules', '@mlightcad');

const KEEP =
  /^\s*(?:(?:static|readonly|abstract|protected|declare|export)\s+)*(?:get |set )?[A-Za-z_$][\w$]*\s*(?:\??\(|\??:|<)/;

for (const rel of process.argv.slice(2)) {
  const file = resolve(ROOT, rel);
  const src = readFileSync(file, 'utf8');
  console.log(`\n##### ${rel}`);
  const lines = src.split('\n');
  let inComment = false;
  for (const raw of lines) {
    const l = raw.replace(/\s+$/, '');
    if (/^\s*\/\*/.test(l)) inComment = true;
    if (inComment) {
      if (/\*\//.test(l)) inComment = false;
      continue;
    }
    if (/^\s*\/\//.test(l) || l.trim() === '') continue;
    if (/^\s*(export |declare )?(abstract )?(class|interface|type|enum|function|const) /.test(l)) {
      console.log(l.trim());
      continue;
    }
    if (/^\s*private /.test(l)) continue;
    if (KEEP.test(l)) console.log('  ' + l.trim());
  }
}
