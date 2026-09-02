/**
 * W1-04 spike — license inventory of the installed dependency tree.
 *
 * Emits out/licenses.json and a Markdown table on stdout. The point of the
 * exercise (CLAUDE.md rule 3) is to prove that the MIT viewer stack
 * (cad-simple-viewer / data-model / three-renderer / mtext-renderer) pulls in
 * no GPL package, and that GPL is confined to @mlightcad/libredwg-*.
 *
 * Run: npm run licenses
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const NM = join(ROOT, 'node_modules');

const tree = JSON.parse(execFileSync('npm', ['ls', '--all', '--json', '--omit=dev'], { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }));

/** name -> { versions:Set, parents:Set } for the production graph only. */
const found = new Map();
function walk(node, parent) {
  for (const [name, dep] of Object.entries(node.dependencies ?? {})) {
    const rec = found.get(name) ?? { versions: new Set(), parents: new Set() };
    if (dep.version) rec.versions.add(dep.version);
    if (parent) rec.parents.add(parent);
    const seen = found.has(name);
    found.set(name, rec);
    if (!seen) walk(dep, name);
    else walk(dep, name);
  }
}
walk(tree, null);

const meta = (name) => {
  const p = join(NM, name, 'package.json');
  if (!existsSync(p)) return {};
  const j = JSON.parse(readFileSync(p, 'utf8'));
  const licenseFiles = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING', 'COPYING.LESSER'].filter((f) =>
    existsSync(join(NM, name, f))
  );
  return {
    license: typeof j.license === 'string' ? j.license : (j.license?.type ?? j.licenses?.[0]?.type ?? 'UNKNOWN'),
    repository: typeof j.repository === 'string' ? j.repository : j.repository?.url,
    licenseFiles,
  };
};

const rows = [...found.entries()]
  .map(([name, rec]) => ({
    name,
    version: [...rec.versions].join(', '),
    ...meta(name),
    parents: [...rec.parents].sort(),
  }))
  .sort((a, b) => a.name.localeCompare(b.name));

const isCopyleft = (l) => /GPL|AGPL|LGPL|MPL|EUPL|CDDL|CPL|EPL|OSL|SSPL/i.test(l ?? '');

// Which packages are reachable WITHOUT touching @mlightcad/libredwg-*?
const mitRoots = [
  '@mlightcad/cad-simple-viewer',
  '@mlightcad/data-model',
  '@mlightcad/three-renderer',
  '@mlightcad/mtext-renderer',
  'three',
  'lodash-es',
];
const reachable = new Set();
(function collect(name) {
  if (reachable.has(name) || name.startsWith('@mlightcad/libredwg-')) return;
  reachable.add(name);
  const p = join(NM, name, 'package.json');
  if (!existsSync(p)) return;
  const j = JSON.parse(readFileSync(p, 'utf8'));
  for (const d of Object.keys({ ...j.dependencies, ...j.peerDependencies })) collect(d);
})('__root__');
reachable.delete('__root__');
for (const r of mitRoots) {
  (function collect(name) {
    if (reachable.has(name) || name.startsWith('@mlightcad/libredwg-')) return;
    reachable.add(name);
    const p = join(NM, name, 'package.json');
    if (!existsSync(p)) return;
    const j = JSON.parse(readFileSync(p, 'utf8'));
    for (const d of Object.keys({ ...j.dependencies, ...j.peerDependencies })) collect(d);
  })(r);
}

const viewerStack = rows.filter((r) => reachable.has(r.name));
const gplInViewerStack = viewerStack.filter((r) => isCopyleft(r.license));
const copyleft = rows.filter((r) => isCopyleft(r.license));

const out = {
  generatedFrom: 'npm ls --all --json --omit=dev inside spikes/mlightcad',
  packageCount: rows.length,
  viewerStackRoots: mitRoots,
  viewerStackPackageCount: viewerStack.length,
  gplInViewerStack: gplInViewerStack.map((r) => `${r.name}@${r.version} (${r.license})`),
  copyleftPackages: copyleft.map((r) => `${r.name}@${r.version} (${r.license})`),
  packages: rows,
};

mkdirSync(join(ROOT, 'out'), { recursive: true });
writeFileSync(join(ROOT, 'out', 'licenses.json'), JSON.stringify(out, null, 2));

console.log(`| package | version | license | pulled in by |`);
console.log(`|---|---|---|---|`);
for (const r of rows) {
  console.log(`| \`${r.name}\` | ${r.version} | ${r.license} | ${r.parents.map((p) => `\`${p}\``).join(', ') || '(direct)'} |`);
}
console.log('');
console.log('viewer-stack packages (excluding libredwg):', viewerStack.length);
console.log('copyleft anywhere:', out.copyleftPackages);
console.log('copyleft inside viewer stack:', out.gplInViewerStack);
