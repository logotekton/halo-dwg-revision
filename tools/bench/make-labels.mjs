#!/usr/bin/env node
/**
 * W3-09 — first draft of `docs/samples/labels.csv`, the sheet-type / floor
 * labels P3 will need.
 *
 * The set has **no paper-space layouts** (measured: all 68 drawings are model
 * space only), so a "sheet" is a title-block INSERT inside model space, not a
 * layout. That makes two of the columns derivable here and one not:
 *
 *   sheet_type   from the file name's Korean keyword (평면/입면/단면/전개/천장/…)
 *   sheets_est   from the count of title-block INSERTs in the drawing
 *   floor        NOT derivable from the file name — every plan file holds all
 *                floors side by side. Left empty with confidence `low`; the real
 *                source is title-block text, which P3 extracts.
 *
 * The user corrects this file; it is a draft, and `confidence` says how much of
 * each row is a guess.
 *
 *   node tools/bench/make-labels.mjs [--reports samples/_reports] [--out docs/samples/labels.csv]
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
let reports = join(ROOT, 'samples', '_reports');
let out = join(ROOT, 'docs', 'samples', 'labels.csv');
for (let i = 2; i < process.argv.length; i++) {
  if (process.argv[i] === '--reports') reports = resolve(process.argv[++i]);
  else if (process.argv[i] === '--out') out = resolve(process.argv[++i]);
}

// macOS hands out directory entries in NFD; every Korean pattern below is NFC,
// so the whole classification silently misses without this normalisation.
const files = JSON.parse(readFileSync(join(reports, 'files.json'), 'utf8')).map((f) => ({
  ...f,
  dir: f.dir.normalize('NFC'),
  name: f.name.normalize('NFC'),
  rel: f.rel.normalize('NFC'),
}));
const cells = JSON.parse(readFileSync(join(reports, 'cells.json'), 'utf8'));

/** Folder -> discipline. The folder is the office's own filing, so it is high confidence. */
const DISCIPLINE = [
  [/^##.*\/00_표지/, '표지'],
  [/^##.*\/01_건축/, '건축'],
  [/^##.*\/02_기계/, '기계'],
  [/^##.*\/03_전기/, '전기'],
  [/^##.*\/04_통신/, '통신'],
  [/^##.*\/05_소방_기계/, '소방(기계)'],
  [/^##.*\/06_소방_전기/, '소방(전기)'],
  [/^##.*\/XR$/, '참조도면(XREF)'],
  [/^#골조샵\/XR$/, '참조도면(XREF)'],
  [/^#골조샵$/, '골조샵(구조)'],
  [/^##실시도서/, '건축(기타)'],
];

/**
 * File-name keyword -> sheet type. Ordered: the first match wins, so the more
 * specific Korean compound ("천장 평면도") has to come before the general one.
 */
const SHEET_TYPE = [
  [/천장\s*평면도|천장/, '천장평면도(RCP)'],
  [/바닥\s*평면도/, '바닥평면도'],
  [/전개도/, '실내전개도'],
  [/입단면도/, '입면·단면도'],
  [/입면도|elevation/i, '입면도'],
  [/단면도/, '단면도'],
  [/평면도|plan(?!t)/i, '평면도'],
  [/창호도|창호위치/, '창호일람표·안내도'],
  [/재료마감표|마감표/, '실내외재료마감표'],
  [/면적산출표/, '면적산출표'],
  [/도면목록표|목록/, '도면목록표'],
  [/일람표/, '일람표'],
  [/제작도/, '제작도(샵)'],
  [/상세도|상세/, '상세도'],
  [/배치도/, '배치도'],
  [/계획도/, '계획도'],
  [/안내도|keymap/i, '안내도·키맵'],
  [/현황도/, '현황도'],
  [/투시도|조감도/, '투시도'],
  [/표지|title/i, '표지·도곽'],
  [/개요/, '건축개요'],
  [/검토/, '검토도'],
  [/코드번호/, '코드일람'],
  [/도서/, '공종 도서(복합)'],
  [/데크|슬라브|슬래브/, '구조상세'],
  [/section/i, '단면도'],
];

const csvCell = (v) => {
  const s = String(v ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

const rows = [];
for (const f of files) {
  const a = cells[`${f.id}|acad`] ?? {};
  const statsPath = join(reports, 'work', `${f.id}.acad.json`);
  let sheets = '';
  let titleBlock = '';
  if (existsSync(statsPath)) {
    try {
      const doc = JSON.parse(readFileSync(statsPath, 'utf8'));
      const byBlock = doc.totals?.insert_by_block ?? {};
      const hits = Object.entries(byBlock).filter(([k]) => /title|도곽|표제/i.test(k));
      if (hits.length) {
        titleBlock = hits.map(([k]) => k).join('|');
        sheets = hits.reduce((s2, [, v]) => s2 + v, 0);
      }
    } catch {
      /* stats missing for this file */
    }
  }
  const discipline = DISCIPLINE.find(([re]) => re.test(f.dir))?.[1] ?? '기타';
  const hit = SHEET_TYPE.find(([re]) => re.test(f.name));
  const sheetType = hit?.[1] ?? '';
  const isXrefDir = /XR$/.test(f.dir);
  const confidence = !sheetType ? 'low' : isXrefDir ? 'medium' : 'medium';
  const notes = [];
  if (isXrefDir) notes.push('XREF 대상 파일(호스트 아님)');
  if (!sheetType) notes.push('파일명에서 시트 유형 추정 불가');
  if (sheets === '') notes.push('표제란 블록 없음 → 도곽 수 미상');
  if (/_recover$/.test(f.name.replace(/\.[^.]+$/, ''))) notes.push('AutoCAD RECOVER 산출 사본(중복 가능)');
  rows.push({
    id: f.id,
    folder: f.dir,
    file: f.name,
    size_mb: (f.bytes / 1048576).toFixed(2),
    discipline,
    sheet_type: sheetType,
    floor: '',
    sheets_est: sheets,
    title_block: titleBlock,
    entities: a.entityCount ?? '',
    layers: a.layers ?? '',
    confidence,
    user_corrected: '',
    notes: notes.join('; '),
  });
}

const header = [
  'id',
  'folder',
  'file',
  'size_mb',
  'discipline',
  'sheet_type',
  'floor',
  'sheets_est',
  'title_block',
  'entities',
  'layers',
  'confidence',
  'user_corrected',
  'notes',
];
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, [header.join(','), ...rows.map((r) => header.map((h) => csvCell(r[h])).join(','))].join('\n') + '\n');
process.stdout.write(`${out}: ${String(rows.length + 1)} lines\n`);
const byType = {};
for (const r of rows) byType[r.sheet_type || '(미상)'] = (byType[r.sheet_type || '(미상)'] ?? 0) + 1;
process.stdout.write(`sheet types: ${JSON.stringify(byType)}\n`);
process.stdout.write(
  `title-block sheets total: ${String(rows.reduce((s2, r) => s2 + (Number(r.sheets_est) || 0), 0))}\n`
);
