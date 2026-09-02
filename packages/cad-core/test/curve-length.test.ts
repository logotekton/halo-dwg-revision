/**
 * The two published routes to a curve length (spike C.2) measured against each
 * other, and against closed-form geometry.
 *
 * `AcDbCurve` has no `length` getter. Route (a) sums the primitives of
 * `subGetIntersectCurves()`; route (b) reads the computed `geometry.length`
 * entry of the property inspector. In 1.14.3 route (b) is published only by
 * LINE, LWPOLYLINE, POLYLINE and ELLIPSE — ARC, CIRCLE and SPLINE return
 * `null`, which this test pins so a future version that adds them is noticed.
 */

import { describe, expect, it } from 'vitest';

import { curveLength, dispose, openDxf } from '../src/index';
import type { CadEntity } from '../src/index';
import { fixtureBytes, sha256Of } from './helpers';

const CURVES = new Set(['LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE']);
const WITHOUT_PROPERTY_LENGTH = new Set(['ARC', 'CIRCLE', 'SPLINE']);

async function modelEntities(file: string): Promise<{ entities: CadEntity[]; close: () => void }> {
  const bytes = fixtureBytes(file);
  const document = await openDxf(bytes, { fileSha256: sha256Of(bytes) });
  const model = document.spaces().find((space) => space.space === 'MODEL');
  return { entities: [...(model?.entities() ?? [])], close: () => { dispose(document); } };
}

describe('curveLength', () => {
  it('agrees between the two routes wherever both are available (±1e-6 relative)', async () => {
    const { entities, close } = await modelEntities('F01.dxf');
    try {
      let compared = 0;
      for (const entity of entities) {
        if (!CURVES.has(entity.type)) continue;
        const viaPrimitives = curveLength(entity, 'intersect-curves');
        const viaProperties = curveLength(entity, 'entity-properties');
        if (WITHOUT_PROPERTY_LENGTH.has(entity.type)) {
          expect(viaProperties, `${entity.type} ${entity.handle}`).toBeNull();
          continue;
        }
        if (viaProperties === null) continue;
        expect(viaPrimitives).not.toBeNull();
        const primitives = viaPrimitives ?? 0;
        expect(primitives).toBeGreaterThan(0);
        expect(Math.abs(primitives - viaProperties) / primitives).toBeLessThanOrEqual(1e-6);
        compared += 1;
      }
      expect(compared).toBeGreaterThanOrEqual(6);
    } finally {
      close();
    }
  });

  it('matches closed-form lengths for CIRCLE, ARC and a bulged polyline', async () => {
    const { entities, close } = await modelEntities('F01.dxf');
    try {
      const byHandle = new Map(entities.map((entity) => [entity.handle, entity]));

      const circle = byHandle.get('A2');
      expect(circle?.type).toBe('CIRCLE');
      const circleDetail = circle?.detail();
      expect(circleDetail?.kind).toBe('CIRCLE');
      if (circleDetail?.kind === 'CIRCLE') {
        expect(curveLength(circle!) ?? 0).toBeCloseTo(2 * Math.PI * circleDetail.radiusMm, 6);
      }

      const arc = byHandle.get('9F');
      expect(arc?.type).toBe('ARC');
      const arcDetail = arc?.detail();
      if (arcDetail?.kind === 'ARC') {
        const sweep = ((arcDetail.endAngleDeg - arcDetail.startAngleDeg + 360) % 360) * (Math.PI / 180);
        expect(curveLength(arc!) ?? 0).toBeCloseTo(sweep * arcDetail.radiusMm, 6);
      }

      // Handle 97 is the LWPOLYLINE carrying a bulge; its length has to be the
      // analytic arc, not the chord (stats contract, "벌지는 해석식").
      const bulged = byHandle.get('97');
      const bulgedDetail = bulged?.detail();
      expect(bulgedDetail?.kind).toBe('LWPOLYLINE');
      if (bulgedDetail?.kind === 'LWPOLYLINE') {
        const bulges = bulgedDetail.vertices.map((vertex) => vertex.bulge);
        expect(bulges.some((bulge) => bulge !== 0)).toBe(true);
        let chords = 0;
        const vertices = bulgedDetail.vertices;
        for (let index = 1; index < vertices.length; index += 1) {
          const a = vertices[index - 1];
          const b = vertices[index];
          if (a && b) chords += Math.hypot(b.x - a.x, b.y - a.y);
        }
        expect(curveLength(bulged!) ?? 0).toBeGreaterThan(chords);
      }
    } finally {
      close();
    }
  });

  it('returns 0 for entities that are not curves', async () => {
    const { entities, close } = await modelEntities('F03.dxf');
    try {
      for (const entity of entities) {
        expect(curveLength(entity), `${entity.type}`).toBe(0);
      }
    } finally {
      close();
    }
  });
});
