/**
 * W1-04 spike — download the third-party assets the spike needs.
 *
 * Everything comes from the mlightcad `cad-data` GitHub repository (served via
 * the jsDelivr GitHub mirror, which is the same origin the viewer uses by
 * default: `https://cdn.jsdelivr.net/gh/mlightcad/cad-data`).
 *
 * Downloads are NOT committed (see .gitignore): SHX fonts are AutoCAD-era
 * proprietary files and the sample DWG is large. URLs and sha256 are recorded
 * in fixtures/assets.lock.json so the docs can cite them.
 *
 * Run: npm run assets
 */
import { createHash } from 'node:crypto';
import { mkdirSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');
const CDN = 'https://cdn.jsdelivr.net/gh/mlightcad/cad-data';

/** Self-hosted font set: the Korean SHX big font plus the chain it needs. */
const FONT_FILES = [
  // Korean big font (encoding euc-kr) used by fixture text style HANGUL
  'whgtxt.shx',
  'whgdtxt.shx',
  // primary SHX referenced by both fixture text styles
  'txt.shx',
  'romans.shx',
  // symbol + CJK mesh fallbacks from the `modern` default preset
  'amgdt.shx',
  'hztxt.shx',
  'simsun.woff',
  'arial.woff',
];

const DOWNLOADS = [
  ...FONT_FILES.map((f) => ({
    url: `${CDN}/fonts/${f}`,
    dest: resolve(ROOT, 'public', 'fonts', f),
    kind: 'font',
  })),
  {
    url: `${CDN}/data/canteen.dwg`,
    dest: resolve(ROOT, 'fixtures', 'canteen.dwg'),
    kind: 'sample-dwg',
  },
];

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex');

const lock = { source: CDN, fetchedAt: new Date().toISOString().slice(0, 10), files: {} };

for (const d of DOWNLOADS) {
  mkdirSync(dirname(d.dest), { recursive: true });
  let bytes;
  if (existsSync(d.dest) && process.env.SPIKE_FORCE !== '1') {
    bytes = readFileSync(d.dest);
    console.log(`skip   ${d.url} (already present)`);
  } else {
    const res = await fetch(d.url);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${d.url}`);
    bytes = Buffer.from(await res.arrayBuffer());
    writeFileSync(d.dest, bytes);
    console.log(`get    ${d.url} → ${bytes.length} bytes`);
  }
  lock.files[d.url] = { kind: d.kind, bytes: bytes.length, sha256: sha256(bytes) };
}

// A self-hosted fonts.json, i.e. the manifest DefaultFontLoader fetches from
// `${AcApDocManager.baseUrl}/fonts/fonts.json`.
const manifest = [
  { file: 'whgtxt.shx', name: ['whgtxt'], type: 'shx', encoding: 'euc-kr' },
  { file: 'whgdtxt.shx', name: ['whgdtxt'], type: 'shx', encoding: 'euc-kr' },
  { file: 'txt.shx', name: ['txt'], type: 'shx' },
  { file: 'romans.shx', name: ['romans'], type: 'shx' },
  { file: 'amgdt.shx', name: ['amgdt'], type: 'shx' },
  { file: 'hztxt.shx', name: ['hztxt'], type: 'shx', encoding: 'gbk' },
  { file: 'simsun.woff', name: ['simsun', '宋体'], type: 'mesh' },
  { file: 'arial.woff', name: ['arial'], type: 'mesh' },
];

// Optional Korean TTF fallback: copied from the local macOS system font set so
// the mesh (TTF) code path can be exercised. Never committed, never shipped.
const APPLE_GOTHIC = '/System/Library/Fonts/Supplemental/AppleGothic.ttf';
if (existsSync(APPLE_GOTHIC)) {
  const bytes = readFileSync(APPLE_GOTHIC);
  writeFileSync(resolve(ROOT, 'public', 'fonts', 'applegothic.ttf'), bytes);
  manifest.push({
    file: 'applegothic.ttf',
    name: ['applegothic', 'AppleGothic', '맑은 고딕', 'malgun'],
    type: 'mesh',
  });
  lock.files[APPLE_GOTHIC] = { kind: 'local-system-font', bytes: bytes.length, sha256: sha256(bytes) };
  console.log(`local  ${APPLE_GOTHIC} → public/fonts/applegothic.ttf`);
} else {
  console.log('note   AppleGothic.ttf not present; the mesh/TTF fallback probe will report unavailable');
}

writeFileSync(resolve(ROOT, 'public', 'fonts', 'fonts.json'), JSON.stringify(manifest, null, 2) + '\n');
writeFileSync(resolve(ROOT, 'fixtures', 'assets.lock.json'), JSON.stringify(lock, null, 2) + '\n');
console.log('wrote public/fonts/fonts.json and fixtures/assets.lock.json');
