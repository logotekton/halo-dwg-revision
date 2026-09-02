/**
 * Performance budget of `docs/briefs/W2-02.md`: layer statistics for F11
 * (~200k entities, ~41 MB) in under 15 seconds.
 *
 * F11 is never committed (`.gitignore`: `fixtures/**\/F11*.dxf`), so this
 * suite is opt-in and skips unless both `HALO_PERF=1` is set and the file is
 * present. To run it:
 *
 *   cd fixtures/gen && uv sync --frozen \
 *     && uv run python -m fixtures_gen --out ../generated --truth /tmp/truth-scratch --only F11
 *   HALO_PERF=1 pnpm --filter @halo-cad/cad-core test
 */

import { describe, expect, it } from 'vitest';

import { dispose, exportNdj, openDxf, statsByLayer } from '../src/index';
import { fixtureBytes, fixtureExists, sha256Of } from './helpers';

const F11 = 'F11.dxf';
const STATS_BUDGET_MS = 15_000;

/**
 * Opt-in: `HALO_PERF=1 pnpm --filter @halo-cad/cad-core test`. F11 is 41 MB and
 * is never committed, so the default suite must not depend on it, and running
 * it inside every `pnpm -r test` pass would add tens of seconds of I/O for a
 * number that only matters when performance changes.
 */
const PERF_ENABLED = process.env['HALO_PERF'] === '1' && fixtureExists(F11);

describe.skipIf(!PERF_ENABLED)('F11 (200k entities)', () => {
  it(`computes layer statistics in under ${String(STATS_BUDGET_MS)} ms`, async () => {
    const bytes = fixtureBytes(F11);
    const sha256 = sha256Of(bytes);
    const openedAt = Date.now();
    const document = await openDxf(bytes, { fileSha256: sha256 });
    const openMs = Date.now() - openedAt;
    try {
      const startedAt = Date.now();
      const stats = statsByLayer(document, { file_sha256: sha256 });
      const statsMs = Date.now() - startedAt;
      const counted = Object.values(stats.totals.count_by_type).reduce((sum, n) => sum + n, 0);
      expect(counted).toBeGreaterThan(150_000);
      expect(statsMs).toBeLessThan(STATS_BUDGET_MS);
      // Recorded so the report can quote real numbers rather than a pass/fail.
      console.log(
        `F11: ${String(counted)} entities, open ${String(openMs)} ms, stats ${String(statsMs)} ms`
      );

      const ndjStartedAt = Date.now();
      const ndj = exportNdj(document, { file_sha256: sha256 });
      console.log(
        `F11: NDJ ${String(ndj.entities.length)} entities in ${String(Date.now() - ndjStartedAt)} ms`
      );
      expect(ndj.entities.length).toBe(counted);
    } finally {
      dispose(document);
    }
  });
});

describe.skipIf(PERF_ENABLED)('F11 (200k entities)', () => {
  it.skip('needs HALO_PERF=1 and fixtures/generated/F11.dxf — see the header of this file', () => {
    /* documented skip */
  });
});
