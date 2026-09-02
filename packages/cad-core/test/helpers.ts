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
 * One `(space, layer)` group of the *old* truth format produced by W1-03's
 * `fixtures_gen.stats`. It is flat, has no ATTRIB and hashes text differently;
 * W2-03 regenerates it in the `LayerStatsDocument` shape. Only the fields the
 * W2-02 brief allows are read from it.
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

export interface TruthStats {
  by_space: Record<string, { by_layer: Record<string, TruthGroup>; totals: TruthGroup }>;
}

export interface TruthEntry {
  file: string;
  dxf_version: string;
  sha256: string;
  stats: TruthStats;
}

interface TruthFile {
  fixture: string;
  primary: TruthEntry | Record<string, TruthEntry>;
}

export function readTruth(fixture: string): TruthFile {
  return JSON.parse(readFileSync(join(TRUTH_DIR, `${fixture}.json`), 'utf8')) as TruthFile;
}

/** `F10` stores two drawings under `primary.grid` / `primary.host`. */
export function truthEntry(fixture: string, part?: string): TruthEntry {
  const truth = readTruth(fixture);
  if (part === undefined) return truth.primary as TruthEntry;
  return (truth.primary as Record<string, TruthEntry>)[part] as TruthEntry;
}

export function truthModelTotals(entry: TruthEntry): TruthGroup {
  const model = entry.stats.by_space['Model'];
  if (!model) throw new Error('truth entry has no Model space');
  return model.totals;
}

export function truthModelLayers(entry: TruthEntry): Record<string, TruthGroup> {
  const model = entry.stats.by_space['Model'];
  if (!model) throw new Error('truth entry has no Model space');
  return model.by_layer;
}

/**
 * `fixtures_gen` keys `count_by_type` by raw DXF record name; the stats
 * contract and `ndj/entity.schema.json` use the normalised NDJ enum, where
 * MULTILEADER is called MLEADER. The rewrite is applied to the truth side so
 * the comparison stays exact instead of being weakened to a subset check.
 */
export function normaliseTruthCounts(counts: Record<string, number>): Record<string, number> {
  const aliases: Record<string, string> = { MULTILEADER: 'MLEADER', TRACE: 'SOLID' };
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(counts)) {
    const mapped = aliases[key] ?? key;
    out[mapped] = (out[mapped] ?? 0) + value;
  }
  return out;
}

export function relativeDelta(actual: number, expected: number): number {
  if (expected === 0) return actual === 0 ? 0 : Number.POSITIVE_INFINITY;
  return Math.abs(actual - expected) / Math.abs(expected);
}
