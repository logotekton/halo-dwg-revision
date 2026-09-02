/**
 * The spline half of the curve-length contract
 * (`docs/contracts/stats-definition.md`: "곡선 길이의 정본은 ezdxf").
 *
 * Reference values were produced with the same ezdxf 1.4.4 the engine pins:
 *
 * ```python
 * doc = ezdxf.readfile('fixtures/generated/F01.dxf')
 * for s in doc.modelspace().query('SPLINE'):
 *     pts = list(s.flattening(0.01))
 *     print(s.dxf.handle, sum((b - a).magnitude for a, b in zip(pts, pts[1:])))
 * # A7 4184.281187 / A8 3939.452637
 * ```
 *
 * Both F01 splines are fit-point splines (group 74 > 0, group 73 == 0), which
 * is the case data-model 1.14.3 reconstructs differently (uniform instead of
 * chord parametrisation) and the reason whitelist entry W01 existed.
 */

import { describe, expect, it } from 'vitest';

import {
  cadFitPointCurve,
  clampedUniformKnots,
  evaluateNurbs,
  flattenNurbs,
  nurbsLength,
  scanSplineFitData,
} from '../src/curve-length';
import { curveLength, dispose, openDxf, statsByLayer } from '../src/index';
import { fixtureBytes, relativeDelta, sha256Of, truthEntry, truthModelLayers } from './helpers';

/** ezdxf `flattening(0.01)` per handle, model space of F01.dxf. */
const EZDXF_SPLINE_LENGTH_MM: Record<string, number> = {
  A7: 4184.281187,
  A8: 3939.452637,
};

/** ezdxf `fit_points_to_cad_cv(...).control_points` for handle A7. */
const EZDXF_A7_CONTROL_POINTS: [number, number][] = [
  [-0.0, -5000.0],
  [307.624669, -4756.520505],
  [953.102684, -4245.636053],
  [1769.27941, -5659.853363],
  [2680.35263, -4371.982371],
  [3298.017145, -4860.942238],
  [3600.0, -5100.0],
];

const EZDXF_A7_KNOTS = [0.0, 0.0, 0.0, 0.0, 0.241334, 0.506384, 0.758666, 1.0, 1.0, 1.0, 1.0];

describe('scanSplineFitData', () => {
  it('recovers the fit points of both F01 splines from the DXF bytes', () => {
    const found = scanSplineFitData(fixtureBytes('F01.dxf'));
    expect([...found.keys()].sort()).toEqual(['A7', 'A8']);
    const a7 = found.get('A7');
    expect(a7?.fitPoints.map((p) => [p.x, p.y])).toEqual([
      [0, -5000],
      [900, -4600],
      [1800, -5200],
      [2700, -4700],
      [3600, -5100],
    ]);
    expect(a7?.startTangent).toBeUndefined();
    expect(a7?.closed).toBe(false);
    expect(found.get('A8')?.fitPoints).toHaveLength(4);
  });

  it('ignores control-point splines and files without splines', () => {
    expect(scanSplineFitData(fixtureBytes('F03.dxf')).size).toBe(0);
    expect(scanSplineFitData(new ArrayBuffer(0)).size).toBe(0);
  });
});

describe('cadFitPointCurve', () => {
  it('reproduces the control points and knots ezdxf computes for A7', () => {
    const fit = scanSplineFitData(fixtureBytes('F01.dxf')).get('A7');
    expect(fit).toBeDefined();
    const curve = cadFitPointCurve(fit!);
    expect(curve).not.toBeNull();
    expect(curve?.degree).toBe(3);
    expect(curve?.controlPoints).toHaveLength(EZDXF_A7_CONTROL_POINTS.length);
    curve?.controlPoints.forEach((control, index) => {
      const [x, y] = EZDXF_A7_CONTROL_POINTS[index]!;
      expect(control.x).toBeCloseTo(x, 4);
      expect(control.y).toBeCloseTo(y, 4);
      expect(control.z).toBeCloseTo(0, 6);
    });
    curve?.knots.forEach((knot, index) => {
      expect(knot).toBeCloseTo(EZDXF_A7_KNOTS[index]!, 5);
    });
  });

  it('passes through every fit point', () => {
    const fit = scanSplineFitData(fixtureBytes('F01.dxf')).get('A7')!;
    const curve = cadFitPointCurve(fit)!;
    const parameters = curve.knots.filter(
      (knot, index, all) => all.indexOf(knot) === index
    );
    // One interpolation node per fit point: the clamped ends plus the interior knots.
    expect(parameters).toHaveLength(fit.fitPoints.length);
    parameters.forEach((parameter, index) => {
      const evaluated = evaluateNurbs(curve, parameter);
      const expected = fit.fitPoints[index]!;
      expect(evaluated.x).toBeCloseTo(expected.x, 5);
      expect(evaluated.y).toBeCloseTo(expected.y, 5);
    });
  });
});

describe('nurbsLength', () => {
  it('matches ezdxf flattening(0.01) for both F01 splines within 1e-6 relative', () => {
    const found = scanSplineFitData(fixtureBytes('F01.dxf'));
    for (const [handle, expected] of Object.entries(EZDXF_SPLINE_LENGTH_MM)) {
      const curve = cadFitPointCurve(found.get(handle)!)!;
      expect(relativeDelta(nurbsLength(curve), expected)).toBeLessThanOrEqual(1e-6);
    }
  });

  it('measures a straight degree-1 spline exactly', () => {
    const length = nurbsLength({
      degree: 1,
      controlPoints: [
        { x: 0, y: 0, z: 0 },
        { x: 300, y: 400, z: 0 },
      ],
      knots: clampedUniformKnots(2, 2),
    });
    expect(length).toBeCloseTo(500, 9);
  });

  it('flattens a full circle expressed as a rational NURBS to 2*pi*r', () => {
    // Quadratic 9-point rational representation of a unit circle
    // (The NURBS Book, example 7.2) scaled to r = 1000.
    const r = 1000;
    const w = Math.SQRT1_2;
    const curve = {
      degree: 2,
      controlPoints: [
        { x: r, y: 0, z: 0 },
        { x: r, y: r, z: 0 },
        { x: 0, y: r, z: 0 },
        { x: -r, y: r, z: 0 },
        { x: -r, y: 0, z: 0 },
        { x: -r, y: -r, z: 0 },
        { x: 0, y: -r, z: 0 },
        { x: r, y: -r, z: 0 },
        { x: r, y: 0, z: 0 },
      ],
      knots: [0, 0, 0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1, 1, 1],
      weights: [1, w, 1, w, 1, w, 1, w, 1],
    };
    expect(relativeDelta(nurbsLength(curve, 0.001), 2 * Math.PI * r)).toBeLessThan(1e-5);
  });

  it('emits a monotonically ordered polyline', () => {
    const fit = scanSplineFitData(fixtureBytes('F01.dxf')).get('A7')!;
    const points = flattenNurbs(cadFitPointCurve(fit)!);
    expect(points.length).toBeGreaterThan(100);
    for (let index = 1; index < points.length; index += 1) {
      expect(points[index]!.x).toBeGreaterThanOrEqual(points[index - 1]!.x - 1e-9);
    }
  });
});

describe('curveLength(SPLINE) after the fit-point rebuild', () => {
  it('is within 0.1% of the ezdxf truth for every F01 spline', async () => {
    const bytes = fixtureBytes('F01.dxf');
    const document = await openDxf(bytes, { fileSha256: sha256Of(bytes) });
    try {
      const model = document.spaces().find((space) => space.space === 'MODEL');
      let measured = 0;
      for (const entity of model?.entities() ?? []) {
        if (entity.type !== 'SPLINE') continue;
        const length = curveLength(entity) ?? 0;
        measured += length;
        const expected = EZDXF_SPLINE_LENGTH_MM[entity.handle.toUpperCase()];
        expect(expected, `unexpected spline handle ${entity.handle}`).toBeDefined();
        expect(relativeDelta(length, expected!)).toBeLessThanOrEqual(0.001);
      }
      const truth = truthModelLayers(truthEntry('F01'))['GEOM-PHTM']?.length_sum ?? 0;
      expect(relativeDelta(measured, truth)).toBeLessThanOrEqual(0.001);
    } finally {
      dispose(document);
    }
  });

  it('brings the whole F01 length_sum_mm inside the ±0.1% contract band', async () => {
    const bytes = fixtureBytes('F01.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const stats = statsByLayer(document, { file_sha256: sha256 });
      const truth = truthEntry('F01').doc.totals.length_sum_mm;
      expect(relativeDelta(stats.totals.length_sum_mm, truth)).toBeLessThanOrEqual(0.001);
    } finally {
      dispose(document);
    }
  });
});
