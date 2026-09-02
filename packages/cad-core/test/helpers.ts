import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** Repository root, four levels up from `packages/cad-core/test`. */
export const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
export const GENERATED_DIR = join(REPO_ROOT, 'fixtures', 'generated');
export const TRUTH_DIR = join(REPO_ROOT, 'fixtures', 'truth');

export function readArrayBuffer(path: string): ArrayBuffer {
  const buffer = readFileSync(path);
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength) as ArrayBuffer;
}

export function fixtureBytes(name: string): ArrayBuffer {
  return readArrayBuffer(join(GENERATED_DIR, name));
}

export function fixtureExists(name: string): boolean {
  return existsSync(join(GENERATED_DIR, name));
}

export function sha256Of(bytes: ArrayBuffer): string {
  return createHash('sha256').update(Buffer.from(bytes)).digest('hex');
}

/**
 * One `(space, layer)` aggregate of the truth format written by W2-03
 * (`LayerStatsDocument`, docs/contracts/stats-definition.md). Field names are
 * mapped onto the short names the tests were written against.
 */
export interface TruthGroup {
  bbox: [number, number, number, number] | null;
  count_by_type: Record<string, number>;
  hatch_area_sum: number;
  insert_by_block: Record<string, number>;
  length_sum: number;
  text_count: number;
  text_hash: string | null;
}

interface TruthAggregate {
  entity_count: number;
  count_by_type: Record<string, number>;
  length_sum_mm: number;
  hatch_area_sum_mm2: number;
  text_count: number;
  text_hash: string;
  insert_by_block: Record<string, number>;
  bbox?: { min: [number, number]; max: [number, number] };
}

interface TruthDocument {
  schema_version: string;
  file_sha256: string;
  producer: { name: string; version: string };
  buckets: { layer: string; space: string; aggregate: TruthAggregate }[];
  totals: TruthAggregate;
}

export interface TruthEntry {
  sha256: string;
  doc: TruthDocument;
}

function toGroup(aggregate: TruthAggregate): TruthGroup {
  return {
    bbox: aggregate.bbox ? [...aggregate.bbox.min, ...aggregate.bbox.max] : null,
    count_by_type: aggregate.count_by_type,
    hatch_area_sum: aggregate.hatch_area_sum_mm2,
    insert_by_block: aggregate.insert_by_block,
    length_sum: aggregate.length_sum_mm,
    text_count: aggregate.text_count,
    text_hash: aggregate.text_hash,
  };
}

/** `F10` is two drawings: `F10_grid.json` / `F10_host.json`. */
export function truthEntry(fixture: string, part?: string): TruthEntry {
  const name = part === undefined ? fixture : `${fixture}_${part}`;
  const doc = JSON.parse(readFileSync(join(TRUTH_DIR, `${name}.json`), 'utf8')) as TruthDocument;
  return { sha256: doc.file_sha256, doc };
}

/** All fixtures draw in model space only, so the document totals are the model totals. */
export function truthModelTotals(entry: TruthEntry): TruthGroup {
  return toGroup(entry.doc.totals);
}

export function truthModelLayers(entry: TruthEntry): Record<string, TruthGroup> {
  const out: Record<string, TruthGroup> = {};
  for (const bucket of entry.doc.buckets) {
    if (bucket.space !== 'MODEL') continue;
    out[bucket.layer] = toGroup(bucket.aggregate);
  }
  return out;
}

/** Both sides use raw DXF record names now (stats contract), so no aliasing. */
export function normaliseTruthCounts(counts: Record<string, number>): Record<string, number> {
  return counts;
}

export function relativeDelta(actual: number, expected: number): number {
  if (expected === 0) return actual === 0 ? 0 : Number.POSITIVE_INFINITY;
  return Math.abs(actual - expected) / Math.abs(expected);
}
