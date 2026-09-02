/**
 * Performance budget of `docs/briefs/W2-02.md`: layer statistics for F11
 * (~200k entities, ~41 MB) in under 15 seconds.
 *
 * F11 is not committed (`.gitignore`: `fixtures/**\/F11*.dxf`), so the test
 * skips when it is absent and reports how to make it:
 *
 *   cd fixtures/gen && uv sync --frozen \
 *     && uv run python -m fixtures_gen --out ../generated --truth /tmp/truth-scratch --only F11
 */

import { describe, expect, it } from 'vitest';

import { dispose, exportNdj, openDxf, statsByLayer } from '../src/index';
import { fixtureBytes, fixtureExists, sha256Of } from './helpers';

const F11 = 'F11.dxf';
const STATS_BUDGET_MS = 15_000;

describe.skipIf(!fixtureExists(F11))('F11 (200k entities)', () => {
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

describe.skipIf(fixtureExists(F11))('F11 (200k entities)', () => {
  it.skip('needs fixtures/generated/F11.dxf — see the header of this file', () => {
    /* documented skip */
  });
});
