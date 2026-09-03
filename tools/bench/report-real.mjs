#!/usr/bin/env node
/**
 * W3-09 — turn the measurement scratch under `samples/_reports/` into the
 * committed inventory document.
 *
 * Input  : files.json + cells.json + browser.jsonl + mlightcad-font-index.json
 *          (all gitignored; produced by `tools/bench-open.mjs --dir`,
 *          `spikes/mlightcad/scripts/bench-real.mjs` and `scan-dxf.mjs`)
 * Output : docs/samples/inventory-<date>.md  and, on stdout, the aggregates the
 *          prose document quotes.
 *
 * **Only aggregate numbers, file names and name statistics are written.** Text
 * bodies never enter the scratch files in the first place (`scan-dxf.mjs`), and
 * this script copies nothing but counts, names and hashes.
 *
 *   node tools/bench/report-real.mjs [--reports samples/_reports] [--out docs/samples/inventory-2026-09-03.md]
 */
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');

function args(argv) {
  const a = { reports: join(ROOT, 'samples', '_reports'), out: null, date: '2026-09-03' };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--reports') a.reports = resolve(argv[++i]);
    else if (argv[i] === '--out') a.out = resolve(argv[++i]);
    else if (argv[i] === '--date') a.date = argv[++i];
    else throw new Error(`unknown argument: ${argv[i]}`);
  }
  a.out ??= join(ROOT, 'docs', 'samples', `inventory-${a.date}.md`);
  return a;
}
const A = args(process.argv.slice(2));

const j = (p, d) => (existsSync(p) ? JSON.parse(readFileSync(p, 'utf8')) : d);
// macOS returns NFD file names; the committed document uses NFC so a reader can
// grep it against the office's own file list.
const files = j(join(A.reports, 'files.json'), []).map((f) => ({
  ...f,
  name: f.name.normalize('NFC'),
  dir: f.dir.normalize('NFC'),
  rel: f.rel.normalize('NFC'),
}));
const cells = j(join(A.reports, 'cells.json'), {});
const fontIndex = j(join(A.reports, 'mlightcad-font-index.json'), { files: [], names: [] });
const browser = new Map();
if (existsSync(join(A.reports, 'browser.jsonl'))) {
  for (const l of readFileSync(join(A.reports, 'browser.jsonl'), 'utf8').split('\n')) {
    if (!l.trim()) continue;
    try {
      const r = JSON.parse(l);
      browser.set(r.id, r);
    } catch {
      /* torn line */
    }
  }
}

const mb = (b) => (typeof b === 'number' ? (b / 1048576).toFixed(2) : '—');
const s = (ms) => (typeof ms === 'number' ? (ms / 1000).toFixed(1) : '—');
const n = (v) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—');
const tier = (v) => (v == null ? '—' : v <= 250_000 ? 'A' : v <= 800_000 ? 'B' : 'C');
/** A cell's one-word verdict, so a FAIL is never mistaken for a missing run. */
const verdict = (ok, err) => (ok === true ? 'ok' : ok === null ? 'n/a' : `FAIL(${String(err ?? '?').split(':')[0]})`);

const rows = files.map((f) => {
  const a = cells[`${f.id}|acad`] ?? {};
  const cv = cells[`${f.id}|acadconv`] ?? {};
  const e = cells[`${f.id}|engine`] ?? {};
  const b = browser.get(f.id) ?? {};
  const bEnt = b.survey?.ok ? b.survey.totalEntities : (b.parse?.entityCount ?? null);
  return { f, a, cv, e, b, bEnt };
});

// --------------------------------------------------------------------------
// 1. set overview
// --------------------------------------------------------------------------
const byVersion = {};
const byFolder = {};
let totalBytes = 0;
for (const { f, a } of rows) {
  const v = a.version ?? a.versionMarker ?? '?';
  byVersion[v] = (byVersion[v] ?? 0) + 1;
  byFolder[f.dir] = (byFolder[f.dir] ?? 0) + 1;
  totalBytes += f.bytes;
}
const codePages = {};
for (const { a } of rows) codePages[a.codePage ?? '?'] = (codePages[a.codePage ?? '?'] ?? 0) + 1;

// --------------------------------------------------------------------------
// 2. parser agreement
// --------------------------------------------------------------------------
let sameAB = 0;
let sameABE = 0;
const typeDelta = {};
const disagree = [];
for (const { f, a, bEnt, e, b } of rows) {
  if (a.entityCount != null && bEnt != null) {
    if (a.entityCount === bEnt) sameAB++;
    else {
      const at = a.countByType ?? {};
      const bt = b.parse?.byType ?? {};
      const d = {};
      for (const k of new Set([...Object.keys(at), ...Object.keys(bt)])) {
        const delta = (bt[k] ?? 0) - (at[k] ?? 0);
        if (delta !== 0) {
          d[k] = delta;
          typeDelta[k] = (typeDelta[k] ?? 0) + delta;
        }
      }
      disagree.push({ id: f.id, name: f.name, acad: a.entityCount, libredwg: bEnt, delta: bEnt - a.entityCount, d });
    }
    if (e.entityCount != null && a.entityCount === bEnt && bEnt === e.entityCount) sameABE++;
  }
}

// --------------------------------------------------------------------------
// 3. fonts (from the acad-ts DXF, the only converter that keeps group 3/4 + XDATA)
// --------------------------------------------------------------------------
const fontFiles = new Map();
const bigFonts = new Map();
const typefaces = new Map();
const styleNames = new Set();
for (const { cv } of rows) {
  for (const st of cv.scan?.styles ?? []) {
    styleNames.add(st.name);
    const add = (m, v) => {
      const k = String(v ?? '').trim();
      if (k) m.set(k, (m.get(k) ?? 0) + 1);
    };
    add(fontFiles, st.font);
    add(bigFonts, st.bigFont);
    add(typefaces, st.typeface);
  }
}
/** cad-data indexes by file name and by bare name; match on the stem, case-insensitively. */
const stem = (x) => x.replace(/\\/g, '/').split('/').pop().replace(/\.[A-Za-z0-9]+$/, '').toLowerCase();
const known = (x) => fontIndex.names.includes(stem(x)) || fontIndex.files.includes(String(x).toLowerCase());
const missingShx = [...fontFiles.entries(), ...bigFonts.entries()].filter(([k]) => !known(k));
const missingMesh = [...typefaces.entries()].filter(([k]) => !known(k));

// --------------------------------------------------------------------------
// 4. XREF graph
// --------------------------------------------------------------------------
const xrefRows = [];
const xrefTargets = new Map();
for (const { f, cv } of rows) {
  for (const x of cv.scan?.xrefs ?? []) {
    const p = x.path ?? '';
    const shape = p === '' ? 'empty' : /^[A-Za-z]:[\\/]/.test(p) ? 'absolute' : /[\\/]/.test(p) ? 'relative' : 'name-only';
    xrefRows.push({ host: f.rel, hostId: f.id, block: x.block, path: p, shape, overlay: x.overlay });
    // macOS stores directory entries in NFD and the DXF carries NFC, so Hangul
    // file names only match after normalising both sides (W3-09: three of eight
    // XREF targets looked missing until this was added).
    const base = (p ? p.replace(/\\/g, '/').split('/').pop() : `${x.block}.dwg`).normalize('NFC');
    xrefTargets.set(base, (xrefTargets.get(base) ?? 0) + 1);
  }
}
const setNames = new Set(files.map((f) => f.name.normalize('NFC')));
const resolvable = [...xrefTargets.keys()].filter((t) => setNames.has(t));
const unresolvable = [...xrefTargets.keys()].filter((t) => !setNames.has(t));

// dxfOut's own view of the same XREF blocks (path preservation check)
let dxfOutXrefTotal = 0;
let dxfOutXrefWithPath = 0;
for (const { e } of rows) {
  for (const x of e.scan?.xrefs ?? []) {
    dxfOutXrefTotal++;
    if ((x.path ?? '') !== '') dxfOutXrefWithPath++;
  }
}

// --------------------------------------------------------------------------
// 5. group-code defects of each converter's DXF
// --------------------------------------------------------------------------
const defect = { dxfOut: { files: 0, ins: 0, ins66: 0, hatch: 0, ext: 0, bigfont0: 0, styles: 0, typeface: 0 }, acad: { files: 0, ins: 0, ins66: 0, hatch: 0, ext: 0, bigfont0: 0, styles: 0, typeface: 0 } };
for (const { e, cv } of rows) {
  for (const [key, cell] of [['dxfOut', e], ['acad', cv]]) {
    const sc = cell.scan;
    if (!sc) continue;
    const d = defect[key];
    d.files++;
    d.ins += sc.insert?.total ?? 0;
    d.ins66 += sc.insert?.withCode66 ?? 0;
    d.hatch += sc.hatch?.boundaryPaths ?? 0;
    d.ext += sc.hatch?.external ?? 0;
    for (const st of sc.styles ?? []) {
      d.styles++;
      if (String(st.bigFont).trim() === '0') d.bigfont0++;
      if (String(st.typeface ?? '').trim()) d.typeface++;
    }
  }
}

// --------------------------------------------------------------------------
// 6. layer-name statistics
// --------------------------------------------------------------------------
const layerFreq = new Map();
let layerTotal = 0;
for (const { cv } of rows) {
  for (const l of cv.scan?.layerNames ?? []) {
    layerFreq.set(l, (layerFreq.get(l) ?? 0) + 1);
    layerTotal++;
  }
}
const layerSorted = [...layerFreq.entries()].sort((x, y) => y[1] - x[1]);
const prefixFreq = new Map();
for (const [name, c] of layerFreq) {
  const p = /^[A-Za-z]-/.test(name) ? name.slice(0, 2) : /^[A-Za-z]{1,3}_/.test(name) ? name.split('_')[0] + '_' : '(other)';
  prefixFreq.set(p, (prefixFreq.get(p) ?? 0) + c);
}

// --------------------------------------------------------------------------
// document
// --------------------------------------------------------------------------
const out = [];
out.push(`# 실제 도서 세트 인벤토리 (${A.date})`);
out.push('');
out.push(
  `자동 생성 문서 — 수정하지 말고 \`node tools/bench/report-real.mjs\`로 다시 만든다. ` +
    `원자료는 \`samples/_reports/\`(gitignore)이고 재현 명령은 다음 두 줄이다.`
);
out.push('');
out.push('```bash');
out.push('node tools/bench-open.mjs --dir "samples/2026-09-02-실시도서" \\');
out.push('     --paths acad,acadconv,dxfout,engine --run-browser --timeout 300 --summary');
out.push('node tools/bench/report-real.mjs');
out.push('```');
out.push('');
out.push(
  '**도면 내용은 이 문서에 없다.** 집계 수치·파일명·폰트명·레이어명 통계·해시만 담는다(W3-09 브리프).'
);
out.push('');
out.push('## 1. 세트 개요');
out.push('');
out.push('| 항목 | 값 |');
out.push('|---|---|');
out.push(`| 도면 파일(.dwg/.dxf, \`.bak\` 제외) | ${String(files.length)} |`);
out.push(`| 합계 크기 | ${mb(totalBytes)} MB (최대 ${mb(Math.max(...files.map((f) => f.bytes)))} MB) |`);
out.push(`| DWG 버전 | ${Object.entries(byVersion).map(([k, v]) => `${k} ${String(v)}`).join(', ')} |`);
out.push(`| \`$DWGCODEPAGE\`(acad-ts \`info\`) | ${Object.entries(codePages).map(([k, v]) => `${k} ${String(v)}`).join(', ')} |`);
out.push(`| 공간 | 전 파일 \`MODEL\` 단독 — 레이아웃(페이퍼공간) 사용 0건 |`);
out.push(`| 폴더 | ${Object.entries(byFolder).map(([k, v]) => `${k} (${String(v)})`).join(', ')} |`);
out.push('');

out.push('## 2. 파일별 표');
out.push('');
out.push(
  '`acad-ts`는 DWG를 직접 읽은 값, `libredwg`는 브라우저 WASM 파서가 돌려준 값, ' +
    '`ezdxf`는 그 파서가 `dxfOut()`으로 쓴 DXF를 엔진이 읽은 값이다. ' +
    '`텍스트`는 `text_count`(TEXT+MTEXT+ATTRIB), `한글`은 그 중 한글 문자를 포함한 문자열 수다.'
);
out.push('');
out.push(
  '| id | 폴더 | 파일 | MB | 버전 | 코드페이지 | acad-ts | libredwg | ezdxf | 텍스트 a/e | 한글 | 레이어 | XREF | 티어 | acad s | 브라우저 s | ezdxf s | ezdxf 결과 |'
);
out.push('|---|---|---|---:|---|---|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|---|');
for (const { f, a, cv, e, b, bEnt } of rows) {
  out.push(
    `| ${f.id} | ${f.dir} | ${f.name} | ${mb(f.bytes)} | ${a.version ?? a.versionMarker ?? '—'} | ${a.codePage ?? '—'} | ` +
      `${n(a.entityCount)} | ${n(bEnt)} | ${n(e.entityCount)} | ${n(a.textCount)}/${n(e.textCount)} | ` +
      `${n(cv.scan?.text?.hangul)} | ${n(a.layers)} | ${String(cv.scan?.xrefs?.length ?? '—')} | ${tier(a.entityCount)} | ` +
      `${s(a.timeMs)} | ${s(b.parse?.ms != null ? Math.round(b.parse.ms) + Math.round(b.dxfOut?.ms ?? 0) : null)} | ${s(e.timeMs)} | ` +
      `${verdict(e.ok, e.error)} |`
  );
}
out.push('');

out.push('## 3. 파서 대조');
out.push('');
out.push('| 항목 | 값 |');
out.push('|---|---|');
out.push(`| acad-ts가 읽은 파일 | ${String(rows.filter((r) => r.a.ok).length)}/${String(files.length)} |`);
out.push(`| libredwg-web이 읽은 파일 | ${String([...browser.values()].filter((b) => b.ok).length)}/${String(files.length)} |`);
out.push(`| \`entity_count\` 완전 일치(acad-ts = libredwg) | ${String(sameAB)}/${String(files.length)} |`);
out.push(`| 세 파서 모두 일치 | ${String(sameABE)}/${String(files.length)} |`);
out.push(
  `| ezdxf가 \`dxfOut()\` DXF를 읽음 | ${String(rows.filter((r) => r.e.ok === true).length)}/${String(rows.filter((r) => r.e.ok !== null).length)} |`
);
out.push(
  `| ezdxf가 acad-ts DXF를 읽음 | ${String(rows.filter((r) => r.cv.engineReads).length)}/${String(rows.filter((r) => r.cv.ok).length)} |`
);
out.push('');
out.push('격차가 있는 파일(음수 = libredwg가 덜 읽음):');
out.push('');
out.push('| id | 파일 | acad-ts | libredwg | 차 | 타입별 |');
out.push('|---|---|---:|---:|---:|---|');
for (const d of disagree) {
  out.push(
    `| ${d.id} | ${d.name} | ${n(d.acad)} | ${n(d.libredwg)} | ${String(d.delta)} | ${Object.entries(d.d).map(([k, v]) => `${k} ${String(v)}`).join(', ')} |`
  );
}
out.push('');
out.push(`합계 타입별 격차: ${Object.entries(typeDelta).map(([k, v]) => `\`${k}\` ${String(v)}`).join(', ')}`);
out.push('');

out.push('## 4. 폰트 (STYLE 테이블 전수)');
out.push('');
out.push(
  `acad-ts \`dwg2dxf\` 산출 DXF에서 집계했다 — 이 경로만 그룹 3(폰트 파일)·4(빅폰트)·` +
    `XDATA \`ACAD\` 1000(TTF typeface)을 모두 보존한다(§6). 스타일 레코드 ${String(defect.acad.styles)}개, ` +
    `고유 스타일명 ${String(styleNames.size)}개.`
);
out.push('');
out.push('### 4.1 SHX / 폰트 파일명 (그룹 3)');
out.push('');
out.push('| 폰트 파일 | 스타일 수 | mlightcad cad-data 보유 |');
out.push('|---|---:|---|');
for (const [k, v] of [...fontFiles.entries()].sort((x, y) => y[1] - x[1])) {
  out.push(`| \`${k}\` | ${String(v)} | ${known(k) ? '있음' : '**누락**'} |`);
}
out.push('');
out.push('### 4.2 빅폰트 (그룹 4)');
out.push('');
out.push('| 빅폰트 | 스타일 수 | cad-data 보유 |');
out.push('|---|---:|---|');
for (const [k, v] of [...bigFonts.entries()].sort((x, y) => y[1] - x[1])) {
  out.push(`| \`${k}\` | ${String(v)} | ${known(k) ? '있음' : '**누락**'} |`);
}
out.push('');
out.push('### 4.3 TTF typeface (STYLE XDATA `ACAD` 1000)');
out.push('');
out.push('| typeface | 스타일 수 | cad-data 보유 |');
out.push('|---|---:|---|');
for (const [k, v] of [...typefaces.entries()].sort((x, y) => y[1] - x[1])) {
  out.push(`| ${k} | ${String(v)} | ${known(k) ? '있음' : '**누락**'} |`);
}
out.push('');
out.push(
  `**누락 요약** — SHX/폰트 파일 ${String(missingShx.length)}종, TTF typeface ${String(missingMesh.length)}종이 ` +
    `mlightcad 기본 폰트 세트(cad-data ${String(fontIndex.files.length)}종)에 없다.`
);
out.push('');

out.push('## 5. XREF');
out.push('');
out.push(`XREF 블록 ${String(xrefRows.length)}건, 대상 파일 ${String(xrefTargets.size)}종.`);
out.push('');
out.push('| 경로 형태 | 건수 |');
out.push('|---|---:|');
const shapes = {};
for (const x of xrefRows) shapes[x.shape] = (shapes[x.shape] ?? 0) + 1;
for (const [k, v] of Object.entries(shapes).sort((a2, b2) => b2[1] - a2[1])) out.push(`| ${k} | ${String(v)} |`);
out.push('');
out.push('| 대상 파일 | 참조 횟수 | 세트 안에 있음 |');
out.push('|---|---:|---|');
for (const [k, v] of [...xrefTargets.entries()].sort((x, y) => y[1] - x[1])) {
  out.push(`| ${k} | ${String(v)} | ${setNames.has(k) ? '예' : '**아니오**'} |`);
}
out.push('');
out.push(`해석 가능 ${String(resolvable.length)}종 / 미해석 ${String(unresolvable.length)}종.`);
out.push('');
out.push('| 호스트 | XREF 블록 | 저장된 경로 | 형태 |');
out.push('|---|---|---|---|');
for (const x of xrefRows) out.push(`| ${x.hostId} ${x.host} | ${x.block} | \`${x.path || '(빈 문자열)'}\` | ${x.shape} |`);
out.push('');

out.push('## 6. 변환기별 그룹코드 보존');
out.push('');
out.push('| 항목 | acad-ts `dwg2dxf` | libredwg + `dxfOut()` |');
out.push('|---|---:|---:|');
out.push(`| 스캔한 DXF 수 | ${String(defect.acad.files)} | ${String(defect.dxfOut.files)} |`);
out.push(`| INSERT 총수 | ${n(defect.acad.ins)} | ${n(defect.dxfOut.ins)} |`);
out.push(`| 그룹 66이 있는 INSERT | ${n(defect.acad.ins66)} | ${n(defect.dxfOut.ins66)} |`);
out.push(`| HATCH 경계 경로 | ${n(defect.acad.hatch)} | ${n(defect.dxfOut.hatch)} |`);
out.push(`| 그 중 External 비트 | ${n(defect.acad.ext)} | ${n(defect.dxfOut.ext)} |`);
out.push(`| STYLE 레코드 | ${n(defect.acad.styles)} | ${n(defect.dxfOut.styles)} |`);
out.push(`| 빅폰트가 \`0\`으로 기록된 STYLE | ${n(defect.acad.bigfont0)} | ${n(defect.dxfOut.bigfont0)} |`);
out.push(`| XDATA typeface를 가진 STYLE | ${n(defect.acad.typeface)} | ${n(defect.dxfOut.typeface)} |`);
out.push(`| XREF 블록 | ${String(xrefRows.length)} | ${String(dxfOutXrefTotal)} |`);
out.push(`| 그 중 경로가 남은 것 | ${String(xrefRows.filter((x) => x.path !== '').length)} | ${String(dxfOutXrefWithPath)} |`);
out.push('');

out.push('## 7. 레이어명 통계');
out.push('');
out.push(`레이어 레코드 ${String(layerTotal)}개, 고유 이름 ${String(layerFreq.size)}개.`);
out.push('');
out.push('| 접두 | 레코드 수 |');
out.push('|---|---:|');
for (const [k, v] of [...prefixFreq.entries()].sort((x, y) => y[1] - x[1]).slice(0, 20)) out.push(`| \`${k}\` | ${String(v)} |`);
out.push('');
out.push('상위 40개 레이어명:');
out.push('');
out.push('| 레이어 | 파일 수 |');
out.push('|---|---:|');
for (const [k, v] of layerSorted.slice(0, 40)) out.push(`| \`${k}\` | ${String(v)} |`);
out.push('');

out.push('## 8. 상위 5장 시간·메모리');
out.push('');
out.push('| id | 파일 | DWG MB | 엔티티 | acad-ts stats s / RSS | acad-ts dwg2dxf s / 출력 MB | libredwg parse s | dxfOut s / 출력 MB | 브라우저 피크 RSS | ezdxf s / RSS | ezdxf 결과 |');
out.push('|---|---|---:|---:|---|---|---:|---|---:|---|---|');
for (const r of [...rows].sort((x, y) => y.f.bytes - x.f.bytes).slice(0, 5)) {
  const { f, a, cv, e, b } = r;
  out.push(
    `| ${f.id} | ${f.name} | ${mb(f.bytes)} | ${n(a.entityCount)} | ${s(a.timeMs)} / ${mb(a.peakRssBytes)} MB | ` +
      `${s(cv.timeMs)} / ${mb(cv.outputBytes)} | ${s(b.parse?.ms)} | ${s(b.dxfOut?.ms)} / ${mb(b.dxfOut?.bytes)} | ` +
      `${mb(b.peakRssBytes)} MB | ${s(e.timeMs)} / ${mb(e.peakRssBytes)} MB | ${verdict(e.ok, e.error)} |`
  );
}
out.push('');

out.push('## 9. 크기 밀도 (티어 1차 추정 계수)');
out.push('');
out.push('| 형식 | 중앙값 B/엔티티 | 최소 | 최대 | 표본 |');
out.push('|---|---:|---:|---:|---:|');
const density = (pick) => {
  const v = rows.map(pick).filter((x) => typeof x === 'number' && Number.isFinite(x) && x > 0).sort((p, q) => p - q);
  return v.length ? [Math.round(v[(v.length - 1) >> 1]), Math.round(v[0]), Math.round(v[v.length - 1]), v.length] : ['—', '—', '—', 0];
};
const dRows = [
  ['원본 DWG (AutoCAD 작성)', density((r) => (r.a.entityCount ? r.f.bytes / r.a.entityCount : null))],
  ['`dxfOut()` 산출 DXF', density((r) => (r.b.parse?.entityCount ? (r.b.dxfOut?.bytes ?? 0) / r.b.parse.entityCount : null))],
  ['acad-ts `dwg2dxf` 산출 DXF', density((r) => (r.a.entityCount ? (r.cv.outputBytes ?? 0) / r.a.entityCount : null))],
];
for (const [name, [med, lo, hi, cnt]] of dRows) out.push(`| ${name} | ${String(med)} | ${String(lo)} | ${String(hi)} | ${String(cnt)} |`);
out.push('');
const bigOnly = rows.filter((r) => r.f.bytes > 2 * 1048576);
const densityBig = (pick) => {
  const v = bigOnly.map(pick).filter((x) => typeof x === 'number' && Number.isFinite(x) && x > 0).sort((p, q) => p - q);
  return v.length ? [Math.round(v[(v.length - 1) >> 1]), Math.round(v[0]), Math.round(v[v.length - 1]), v.length] : ['—', '—', '—', 0];
};
const dBigRows = [
  ['원본 DWG (>2 MB만)', densityBig((r) => (r.a.entityCount ? r.f.bytes / r.a.entityCount : null))],
  ['`dxfOut()` DXF (>2 MB만)', densityBig((r) => (r.b.parse?.entityCount ? (r.b.dxfOut?.bytes ?? 0) / r.b.parse.entityCount : null))],
  ['acad-ts DXF (>2 MB만)', densityBig((r) => (r.a.entityCount ? (r.cv.outputBytes ?? 0) / r.a.entityCount : null))],
];
for (const [name, [med, lo, hi, cnt]] of dBigRows) out.push(`| ${name} | ${String(med)} | ${String(lo)} | ${String(hi)} | ${String(cnt)} |`);
out.push('');
out.push(
  '작은 도면은 로고 이미지·표제란 XREF·테이블 같은 고정비가 크기를 지배해서 B/엔티티가 ' +
    '수천까지 치솟는다. 1차 추정 계수는 내용이 크기를 지배하는 >2 MB 표본에서 읽어야 한다.'
);
out.push('');

// text fidelity between the two converter outputs
const textCmp = { both: 0, sameCount: 0, sameHash: 0 };
let mojiAcad = 0;
let mojiDxfOut = 0;
let hangulAcad = 0;
let hangulDxfOut = 0;
for (const { a, e, cv } of rows) {
  if (cv.scan) {
    mojiAcad += cv.scan.text?.mojibake ?? 0;
    hangulAcad += cv.scan.text?.hangul ?? 0;
  }
  if (e.scan) {
    mojiDxfOut += e.scan.text?.mojibake ?? 0;
    hangulDxfOut += e.scan.text?.hangul ?? 0;
  }
  if (a.ok && e.ok) {
    textCmp.both++;
    if (a.textCount === e.textCount) textCmp.sameCount++;
    if (a.textHash === e.textHash) textCmp.sameHash++;
  }
}
out.push('## 10. 한글 텍스트와 인코딩');
out.push('');
out.push('| 항목 | acad-ts DXF | `dxfOut()` DXF |');
out.push('|---|---:|---:|');
out.push(`| 한글 포함 문자열 | ${n(hangulAcad)} | ${n(hangulDxfOut)} |`);
out.push(`| 모지바케 의심 문자열 | ${n(mojiAcad)} | ${n(mojiDxfOut)} |`);
out.push('');
out.push(
  `양쪽 stats가 모두 성공한 ${String(textCmp.both)}개 파일에서 \`text_count\` 일치 ${String(textCmp.sameCount)}건, ` +
    `\`text_hash\` 일치 ${String(textCmp.sameHash)}건.`
);
out.push('');

const tiers = { A: 0, B: 0, C: 0 };
for (const { a } of rows) tiers[tier(a.entityCount)] = (tiers[tier(a.entityCount)] ?? 0) + 1;
out.push(`티어 분포(엔티티 수 기준, ADR-0002 개정 §5): A ${String(tiers.A)} · B ${String(tiers.B)} · C ${String(tiers.C)}.`);
out.push('');

mkdirSync(dirname(A.out), { recursive: true });
writeFileSync(A.out, out.join('\n'));

// --------------------------------------------------------------------------
// stdout: the aggregates the prose document quotes
// --------------------------------------------------------------------------
const log = (...x) => process.stdout.write(x.join(' ') + '\n');
log(`wrote ${A.out} (${String(out.length)} lines)`);
log(`files=${String(files.length)} totalMB=${mb(totalBytes)} versions=${JSON.stringify(byVersion)} codepages=${JSON.stringify(codePages)}`);
log(`entity-count agreement acad-ts==libredwg ${String(sameAB)}/${String(files.length)}; all three ${String(sameABE)}`);
log(`type deltas ${JSON.stringify(typeDelta)}`);
log(`ezdxf reads dxfOut DXF ${String(rows.filter((r) => r.e.ok === true).length)}/${String(rows.filter((r) => r.e.ok !== null).length)}`);
log(`ezdxf reads acad-ts DXF ${String(rows.filter((r) => r.cv.engineReads).length)}/${String(rows.filter((r) => r.cv.ok).length)}`);
log(`missing SHX/font files: ${missingShx.map(([k, v]) => `${k}(${String(v)})`).join(', ')}`);
log(`missing TTF typefaces: ${missingMesh.map(([k, v]) => `${k}(${String(v)})`).join(', ')}`);
log(`xref blocks ${String(xrefRows.length)}, targets ${String(xrefTargets.size)}, resolvable ${String(resolvable.length)}, unresolvable ${unresolvable.join('|')}`);
log(`dxfOut xref paths kept ${String(dxfOutXrefWithPath)}/${String(dxfOutXrefTotal)}; acad-ts ${String(xrefRows.filter((x) => x.path !== '').length)}/${String(xrefRows.length)}`);
log(`INSERT 66: acad-ts ${String(defect.acad.ins66)}/${String(defect.acad.ins)}, dxfOut ${String(defect.dxfOut.ins66)}/${String(defect.dxfOut.ins)}`);
log(`HATCH external: acad-ts ${String(defect.acad.ext)}/${String(defect.acad.hatch)}, dxfOut ${String(defect.dxfOut.ext)}/${String(defect.dxfOut.hatch)}`);
log(`STYLE bigfont written as "0": acad-ts ${String(defect.acad.bigfont0)}, dxfOut ${String(defect.dxfOut.bigfont0)} (of ${String(defect.dxfOut.styles)})`);
log(`STYLE XDATA typeface kept: acad-ts ${String(defect.acad.typeface)}, dxfOut ${String(defect.dxfOut.typeface)}`);
log(`tiers ${JSON.stringify(tiers)}`);
for (const [name, [med, lo, hi, cnt]] of dRows) log(`density ${name}: median ${String(med)} B/entity (min ${String(lo)}, max ${String(hi)}, n=${String(cnt)})`);
for (const [name, [med, lo, hi, cnt]] of dBigRows) log(`density>2MB ${name}: median ${String(med)} (min ${String(lo)}, max ${String(hi)}, n=${String(cnt)})`);
log(`hangul strings acad-ts ${String(hangulAcad)} / dxfOut ${String(hangulDxfOut)}; mojibake ${String(mojiAcad)} / ${String(mojiDxfOut)}`);
log(`text agreement (both stats ok, n=${String(textCmp.both)}): count ${String(textCmp.sameCount)}, hash ${String(textCmp.sameHash)}`);
log(`xref unresolvable after NFC: ${unresolvable.join('|') || '(none)'}`);
log(`layers: ${String(layerFreq.size)} unique of ${String(layerTotal)} records`);
