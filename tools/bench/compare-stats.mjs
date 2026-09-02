/**
 * W2-06 — conversion-fidelity comparison for tools/bench-open.mjs.
 *
 * Compares a `LayerStatsDocument` (packages/schema/src/stats/layer-stats.schema.json)
 * against `fixtures/truth/<F>.json`, which W2-03 made a LayerStatsDocument itself.
 * The fields are the ones ADR-0002 §6 crosschecks, plus the two the W2-06 brief
 * singles out: `text_count`/`text_hash` (Korean text survival) and
 * `insert_by_block` (the X-TITLE INSERT that acad-ts's DWG writer drops when a
 * block and a layer share a name).
 *
 * Sums are compared with a relative tolerance (the crosscheck contract's ±0.1%);
 * counts, hashes and maps must be exact.
 */
export const SUM_TOLERANCE = 0.001;

const isObj = (v) => v !== null && typeof v === 'object';

function mapDiff(a = {}, b = {}) {
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])].sort();
  const diff = {};
  for (const k of keys) {
    const x = a[k] ?? 0;
    const y = b[k] ?? 0;
    if (x !== y) diff[k] = { got: x, want: y };
  }
  return diff;
}

function sumClose(got, want) {
  if (typeof got !== 'number' || typeof want !== 'number') return false;
  if (want === 0) return Math.abs(got) < 1e-6;
  return Math.abs(got - want) / Math.abs(want) <= SUM_TOLERANCE;
}

function relPct(got, want) {
  if (typeof got !== 'number' || typeof want !== 'number' || want === 0) return null;
  return ((got - want) / want) * 100;
}

/**
 * @param got  LayerStatsDocument produced by one converter path
 * @param want LayerStatsDocument from fixtures/truth
 * @returns {{ok: boolean, checks: object, summary: string}}
 */
export function compareStats(got, want) {
  if (!isObj(got) || !isObj(want)) {
    return { ok: false, checks: {}, summary: 'missing stats document' };
  }
  const g = got.totals ?? {};
  const w = want.totals ?? {};

  const checks = {
    entity_count: { got: g.entity_count, want: w.entity_count, ok: g.entity_count === w.entity_count },
    count_by_type: { diff: mapDiff(g.count_by_type, w.count_by_type) },
    length_sum_mm: {
      got: g.length_sum_mm,
      want: w.length_sum_mm,
      deltaPct: relPct(g.length_sum_mm, w.length_sum_mm),
      ok: sumClose(g.length_sum_mm, w.length_sum_mm),
    },
    hatch_area_sum_mm2: {
      got: g.hatch_area_sum_mm2,
      want: w.hatch_area_sum_mm2,
      deltaPct: relPct(g.hatch_area_sum_mm2, w.hatch_area_sum_mm2),
      ok: sumClose(g.hatch_area_sum_mm2, w.hatch_area_sum_mm2),
    },
    text_count: { got: g.text_count, want: w.text_count, ok: g.text_count === w.text_count },
    text_hash: { got: g.text_hash, want: w.text_hash, ok: g.text_hash === w.text_hash },
    insert_by_block: { diff: mapDiff(g.insert_by_block, w.insert_by_block) },
  };
  checks.count_by_type.ok = Object.keys(checks.count_by_type.diff).length === 0;
  checks.insert_by_block.ok = Object.keys(checks.insert_by_block.diff).length === 0;

  // Per-bucket (space, layer) exactness -- a path can get the totals right while
  // moving entities between layers.
  const key = (b) => `${b.space}|${b.layer}`;
  const gb = new Map((got.buckets ?? []).map((b) => [key(b), b.aggregate]));
  const wb = new Map((want.buckets ?? []).map((b) => [key(b), b.aggregate]));
  const bucketProblems = [];
  for (const [k, wa] of wb) {
    const ga = gb.get(k);
    if (!ga) {
      bucketProblems.push(`${k}: missing`);
      continue;
    }
    if (ga.entity_count !== wa.entity_count) {
      bucketProblems.push(`${k}: entity_count ${String(ga.entity_count)}≠${String(wa.entity_count)}`);
    }
    if (ga.text_hash !== wa.text_hash) bucketProblems.push(`${k}: text_hash`);
  }
  for (const k of gb.keys()) if (!wb.has(k)) bucketProblems.push(`${k}: extra`);
  checks.buckets = { ok: bucketProblems.length === 0, problems: bucketProblems.slice(0, 12) };

  const ok = Object.values(checks).every((c) => c.ok);
  const mark = (c) => (c.ok ? 'ok' : 'FAIL');
  const summary = [
    `count=${mark(checks.entity_count)}`,
    `type=${mark(checks.count_by_type)}`,
    `len=${mark(checks.length_sum_mm)}`,
    `hatch=${mark(checks.hatch_area_sum_mm2)}`,
    `text=${mark(checks.text_count)}`,
    `hash=${mark(checks.text_hash)}`,
    `insert=${mark(checks.insert_by_block)}`,
    `buckets=${mark(checks.buckets)}`,
  ].join(' ');
  return { ok, checks, summary };
}

/** Short human cell for the markdown table. */
export function fidelityCell(fid) {
  if (!fid) return '—';
  if (fid.error) return `n/a (${fid.error})`;
  if (fid.ok) return 'exact';
  const bad = [];
  const c = fid.checks;
  if (!c.entity_count.ok) bad.push(`count ${String(c.entity_count.got)}≠${String(c.entity_count.want)}`);
  if (!c.count_by_type.ok) {
    bad.push(
      'type ' +
        Object.entries(c.count_by_type.diff)
          .map(([k, v]) => `${k} ${String(v.got)}≠${String(v.want)}`)
          .join(', ')
    );
  }
  if (!c.length_sum_mm.ok) bad.push(`len ${c.length_sum_mm.deltaPct?.toFixed(2) ?? '?'}%`);
  if (!c.hatch_area_sum_mm2.ok) bad.push(`hatch ${c.hatch_area_sum_mm2.deltaPct?.toFixed(2) ?? '?'}%`);
  if (!c.text_count.ok) bad.push(`text_count ${String(c.text_count.got)}≠${String(c.text_count.want)}`);
  if (!c.text_hash.ok) bad.push('text_hash≠');
  if (!c.insert_by_block.ok) {
    bad.push(
      'insert ' +
        Object.entries(c.insert_by_block.diff)
          .map(([k, v]) => `${k} ${String(v.got)}≠${String(v.want)}`)
          .join(', ')
    );
  }
  return bad.join('; ') || 'differs';
}
