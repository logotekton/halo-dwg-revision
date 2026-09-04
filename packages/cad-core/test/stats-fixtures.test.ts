/**
 * `statsByLayer` against the W1-03 fixtures and their ezdxf truth.
 *
 * The truth files are still in the *old* flat format (`fixtures_gen.stats`),
 * so per `docs/briefs/W2-02.md` only `count_by_type`, `length_sum`,
 * `hatch_area_sum`, `insert_by_block` and `bbox` are compared; `text_count`,
 * `text_hash` and the bucket layout are left to W2-03 / W2-04.
 *
 * One measured cross-parser gap is encoded below instead of being hidden by a
 * loose tolerance (the `length_sum` gap of the W2-02 report is gone: W3-02
 * replaced the spline length with our own ezdxf-compatible flattening):
 *
 * 1. `bbox` — extents of TEXT, MTEXT, INSERT, DIMENSION, LEADER, MLEADER and
 *    SPLINE are derived (font metrics, block expansion, curve approximation)
 *    and the two parsers disagree by tens to hundreds of millimetres. Buckets
 *    made only of exactly-representable geometry are held to the contract's
 *    ±1 mm; the rest are held to a recorded per-fixture bound so a regression
 *    still fails the suite.
 */

import { assertValid, validateLayerStats } from '@halo-cad/schema';
import { describe, expect, it } from 'vitest';

import { dispose, openDxf, statsByLayer } from '../src/index';
import type { CadDocumentHandle } from '../src/index';
import {
  fixtureBytes,
  normaliseTruthCounts,
  relativeDelta,
  sha256Of,
  truthEntry,
  truthModelLayers,
  truthModelTotals,
} from './helpers';
import type { TruthGroup } from './helpers';

/** Entity types whose bounding box is derived rather than stored. */
const APPROXIMATE_EXTENTS: ReadonlySet<string> = new Set([
  'TEXT',
  'MTEXT',
  'ATTRIB',
  'ATTDEF',
  'INSERT',
  'DIMENSION',
  'LEADER',
  'MLEADER',
  'MULTILEADER',
  'SPLINE',
  'PROXY',
]);

/** Contract tolerance for a bucket built only from exact geometry. */
const BBOX_EXACT_MM = 1;

interface Case {
  id: string;
  file: string;
  truthId: string;
  truthPart?: string;
  /** Recorded deviation bound of the totals bbox, in mm (see the header note). */
  bboxTotalsMm: number;
}

const CASES: Case[] = [
  { id: 'F01', file: 'F01.dxf', truthId: 'F01', bboxTotalsMm: BBOX_EXACT_MM },
  { id: 'F02', file: 'F02.dxf', truthId: 'F02', bboxTotalsMm: 362 },
  { id: 'F03', file: 'F03.dxf', truthId: 'F03', bboxTotalsMm: 158 },
  { id: 'F04', file: 'F04.dxf', truthId: 'F04', bboxTotalsMm: BBOX_EXACT_MM },
  { id: 'F05', file: 'F05.dxf', truthId: 'F05', bboxTotalsMm: 67 },
  { id: 'F06', file: 'F06.dxf', truthId: 'F06', bboxTotalsMm: 195 },
  { id: 'F07', file: 'F07.dxf', truthId: 'F07', bboxTotalsMm: 141 },
  { id: 'F08', file: 'F08.dxf', truthId: 'F08', bboxTotalsMm: 397 },
  { id: 'F09', file: 'F09.dxf', truthId: 'F09', bboxTotalsMm: BBOX_EXACT_MM },
  { id: 'F10-grid', file: 'F10_grid.dxf', truthId: 'F10', truthPart: 'grid', bboxTotalsMm: 195 },
  { id: 'F10-host', file: 'F10_host.dxf', truthId: 'F10', truthPart: 'host', bboxTotalsMm: 43 },
];

function bboxDelta(
  actual: { min: number[]; max: number[] } | undefined,
  expected: TruthGroup['bbox']
): number {
  if (!expected) return actual === undefined ? 0 : Number.POSITIVE_INFINITY;
  if (!actual) return Number.POSITIVE_INFINITY;
  const mine = [actual.min[0], actual.min[1], actual.max[0], actual.max[1]];
  let worst = 0;
  for (let index = 0; index < 4; index += 1) {
    worst = Math.max(worst, Math.abs((mine[index] ?? Number.NaN) - (expected[index] ?? Number.NaN)));
  }
  return worst;
}

function isExactBucket(countByType: Record<string, number>): boolean {
  return Object.keys(countByType).every((type) => !APPROXIMATE_EXTENTS.has(type));
}

async function open(file: string): Promise<{ document: CadDocumentHandle; sha256: string }> {
  const bytes = fixtureBytes(file);
  const sha256 = sha256Of(bytes);
  return { document: await openDxf(bytes, { fileSha256: sha256 }), sha256 };
}

describe.each(CASES)('statsByLayer $id', (testCase) => {
  it('produces a schema-valid document that agrees with the ezdxf truth', async () => {
    const { document, sha256 } = await open(testCase.file);
    try {
      const stats = statsByLayer(document, { file_sha256: sha256 });
      assertValid(validateLayerStats, stats, `${testCase.id} layer stats`);

      const entry = truthEntry(testCase.truthId, testCase.truthPart);
      expect(sha256).toBe(entry.sha256);
      const truthTotals = truthModelTotals(entry);

      // --- counts and blocks: exact ------------------------------------
      expect(stats.totals.count_by_type).toEqual(normaliseTruthCounts(truthTotals.count_by_type));
      expect(stats.totals.insert_by_block).toEqual(truthTotals.insert_by_block);
      const summed = Object.values(stats.totals.count_by_type).reduce((sum, n) => sum + n, 0);
      expect(stats.totals.entity_count).toBe(summed);

      // --- hatch area: +/-0.5% -----------------------------------------
      expect(relativeDelta(stats.totals.hatch_area_sum_mm2, truthTotals.hatch_area_sum)).toBeLessThanOrEqual(
        0.005
      );

      // --- length: +/-0.1% against the ezdxf truth, no exceptions ---------
      // W3-02 closed the last gap: SPLINE length now comes from this package's
      // own NURBS flattening (`src/curve-length.ts`), rebuilt from the fit
      // points in the file exactly as ezdxf does, so F01 needs no correction
      // term any more (whitelist W01 is retired).
      expect(relativeDelta(stats.totals.length_sum_mm, truthTotals.length_sum)).toBeLessThanOrEqual(
        0.001
      );

      // --- bbox ----------------------------------------------------------
      expect(bboxDelta(stats.totals.bbox, truthTotals.bbox)).toBeLessThanOrEqual(testCase.bboxTotalsMm);

      // --- per layer ------------------------------------------------------
      const truthLayers = truthModelLayers(entry);
      const modelBuckets = stats.buckets.filter((bucket) => bucket.space === 'MODEL');
      expect(modelBuckets.map((bucket) => bucket.layer).sort()).toEqual(Object.keys(truthLayers).sort());
      for (const bucket of modelBuckets) {
        const expected = truthLayers[bucket.layer];
        expect(expected, `layer ${bucket.layer}`).toBeDefined();
        if (!expected) continue;
        expect(bucket.aggregate.count_by_type, `layer ${bucket.layer} counts`).toEqual(
          normaliseTruthCounts(expected.count_by_type)
        );
        expect(bucket.aggregate.insert_by_block, `layer ${bucket.layer} blocks`).toEqual(
          expected.insert_by_block
        );
        expect(
          relativeDelta(bucket.aggregate.hatch_area_sum_mm2, expected.hatch_area_sum),
          `layer ${bucket.layer} hatch area`
        ).toBeLessThanOrEqual(0.005);
        // Text extents are font-dependent, so ATTRIB-only layers are approximate too.
        if (isExactBucket(bucket.aggregate.count_by_type) && bucket.aggregate.text_count === 0) {
          expect(
            bboxDelta(bucket.aggregate.bbox, expected.bbox),
            `layer ${bucket.layer} bbox`
          ).toBeLessThanOrEqual(BBOX_EXACT_MM);
        }
      }
    } finally {
      dispose(document);
    }
  });
});

describe('statsByLayer determinism and encoding', () => {
  it('is byte-identical across two runs on the same bytes (CLAUDE.md rule 7)', async () => {
    const bytes = fixtureBytes('F06.dxf');
    const sha256 = sha256Of(bytes);
    const first = await openDxf(bytes, { fileSha256: sha256 });
    const second = await openDxf(bytes, { fileSha256: sha256 });
    try {
      expect(JSON.stringify(statsByLayer(first, { file_sha256: sha256 }))).toBe(
        JSON.stringify(statsByLayer(second, { file_sha256: sha256 }))
      );
    } finally {
      dispose(first);
      dispose(second);
    }
  });

  it('reads the same Korean text from the CP949 R2000 variant as from R2018 (F03)', async () => {
    const utf8Bytes = fixtureBytes('F03.dxf');
    const cp949Bytes = fixtureBytes('F03_r2000_cp949.dxf');
    const utf8 = await openDxf(utf8Bytes, { fileSha256: sha256Of(utf8Bytes) });
    const cp949 = await openDxf(cp949Bytes, { fileSha256: sha256Of(cp949Bytes) });
    try {
      expect(utf8.header.codepageDeclared).toBe('ANSI_1252');
      expect(cp949.header.dwgVersion).toBe('AC1015');
      expect(cp949.header.codepageDeclared).toBe('ANSI_949');
      // mlightcad maps `ANSI_949` onto the WHATWG label `euc-kr`, which is the
      // decoder it actually uses for the Korean Wansung code page.
      expect(cp949.header.codepageEffective).toBe('euc-kr');

      const texts = (document: CadDocumentHandle): string[] => {
        const out: string[] = [];
        for (const space of document.spaces()) {
          for (const entity of space.entities()) {
            const value = entity.textValue();
            if (value !== null) out.push(value.normalize('NFC'));
          }
        }
        return out.sort();
      };
      const fromUtf8 = texts(utf8);
      expect(fromUtf8.join('\n')).toContain('거실');
      expect(texts(cp949)).toEqual(fromUtf8);
    } finally {
      dispose(utf8);
      dispose(cp949);
    }
  });

  it('carries the XREF block of the F10 host into insert_by_block', async () => {
    const bytes = fixtureBytes('F10_host.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const stats = statsByLayer(document, { file_sha256: sha256 });
      expect(stats.totals.insert_by_block['F10_GRID']).toBe(1);
      const blocks = document.blocks().filter((block) => block.isXref);
      expect(blocks.map((block) => block.name)).toEqual(['F10_GRID']);
      expect(blocks[0]?.xrefPath).toBe('F10_grid.dxf');
      expect(blocks[0]?.isUnresolvedXref).toBe(true);
    } finally {
      dispose(document);
    }
  });
});
