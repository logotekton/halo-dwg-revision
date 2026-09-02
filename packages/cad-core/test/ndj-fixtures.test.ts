/**
 * `exportNdj` against the W1-03 fixtures.
 *
 * The contract checks are: the document validates against
 * `ndj/document.schema.json`, every entity is accounted for by the layer
 * statistics, and provenance is complete (CLAUDE.md rule 6).
 */

import { assertValid, validateNdjDocument, validateNdjEntity } from '@halo-cad/schema';
import { describe, expect, it } from 'vitest';

import { dispose, exportNdj, openDxf, statsByLayer, toNdjsonLines } from '../src/index';
import { fixtureBytes, sha256Of } from './helpers';

const FIXTURES = [
  'F01.dxf',
  'F02.dxf',
  'F03.dxf',
  'F04.dxf',
  'F05.dxf',
  'F06.dxf',
  'F07.dxf',
  'F08.dxf',
  'F09.dxf',
  'F10_grid.dxf',
  'F10_host.dxf',
  'F01_r2000_cp949.dxf',
  'F04_r2000_cp949.dxf',
  'F05_r2000_cp949.dxf',
];

describe.each(FIXTURES)('exportNdj %s', (file) => {
  it('emits a schema-valid document whose entity count matches the statistics', async () => {
    const bytes = fixtureBytes(file);
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const ndj = exportNdj(document, { file_sha256: sha256 });
      assertValid(validateNdjDocument, ndj, `${file} NDJ`);

      const stats = statsByLayer(document, { file_sha256: sha256 });
      const counted = Object.values(stats.totals.count_by_type).reduce((sum, n) => sum + n, 0);
      // ATTRIB entities appear in the stream under their own handles but are
      // never counted in `count_by_type` (stats contract); everything else is
      // one-to-one with the statistics.
      const attribs = ndj.entities.filter((entity) => entity.type === 'ATTRIB').length;
      expect(ndj.entities.length - attribs).toBe(counted);

      for (const entity of ndj.entities) {
        expect(entity.provenance.file).toBe(sha256);
        expect(entity.provenance.handle).toMatch(/^[0-9A-F]{1,16}$/);
        expect(entity.provenance.space).toMatch(/^(MODEL|PAPER:.+)$/);
      }

      expect(ndj.header.file_sha256).toBe(sha256);
      expect(ndj.header.producer?.name).toBe('viewer.mlightcad');
      expect(ndj.header.layouts.some((layout) => layout.is_model)).toBe(true);
    } finally {
      dispose(document);
    }
  });
});

describe('exportNdj shape', () => {
  it('keeps every entity individually valid and serialises as NDJSON', async () => {
    const bytes = fixtureBytes('F05.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const ndj = exportNdj(document, { file_sha256: sha256 });
      for (const entity of ndj.entities) {
        assertValid(validateNdjEntity, entity, `${entity.type} ${entity.provenance.handle}`);
      }
      const types = new Set(ndj.entities.map((entity) => entity.type));
      expect(types).toContain('DIMENSION');
      expect(types).toContain('LEADER');
      expect(types).toContain('MLEADER');

      const lines = toNdjsonLines(ndj).trimEnd().split('\n');
      expect(lines).toHaveLength(ndj.entities.length + 1);
      expect(JSON.parse(lines[0] ?? '{}')).toHaveProperty('header');
    } finally {
      dispose(document);
    }
  });

  it('records hatch loops with the outer loop first and holes after it', async () => {
    const bytes = fixtureBytes('F04.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const ndj = exportNdj(document, { file_sha256: sha256 });
      const hatches = ndj.entities.filter((entity) => entity.type === 'HATCH');
      expect(hatches).toHaveLength(9);
      const withHole = hatches.filter((entity) => entity.boundary_loops.length > 1);
      expect(withHole.length).toBeGreaterThanOrEqual(2);
      for (const hatch of hatches) {
        expect(hatch.boundary_loops[0]?.is_outer).toBe(true);
        for (const loop of hatch.boundary_loops.slice(1)) expect(loop.is_outer).toBe(false);
        expect(hatch.area_mm2).toBeGreaterThan(0);
      }
      // Net area (outer minus hole) is what both parsers sum.
      const holed = withHole[0];
      expect(holed?.area_mm2).toBe(1200000);
    } finally {
      dispose(document);
    }
  });

  it('maps unknown DXF records onto PROXY with their original type', async () => {
    const bytes = fixtureBytes('F05.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const ndj = exportNdj(document, { file_sha256: sha256 });
      for (const entity of ndj.entities) {
        if (entity.type !== 'PROXY') continue;
        expect(entity.original_type).toBeTruthy();
      }
      // MULTILEADER is renamed, not proxied.
      expect(ndj.entities.some((entity) => entity.type === 'MLEADER')).toBe(true);
    } finally {
      dispose(document);
    }
  });
});
