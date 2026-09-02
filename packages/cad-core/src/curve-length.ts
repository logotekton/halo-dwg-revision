/**
 * NURBS evaluation, adaptive flattening and SPLINE fit-point recovery.
 *
 * `docs/contracts/stats-definition.md` names **ezdxf the reference** for curve
 * length: the crosscheck whitelist entry W01 exists because mlightcad's
 * `AcGeSpline3d.length` is ~11% larger than ezdxf's on F01. Measuring that gap
 * (W3-02) showed it is *not* a length-algorithm difference — flattening
 * mlightcad's own curve reproduces its `length` to 3e-5% — but a **different
 * curve**: for a SPLINE defined by fit points (DXF group 74 > 0, group 73 == 0)
 * mlightcad interpolates with a uniform parametrisation while AutoCAD,
 * BricsCAD and ezdxf use the chord-length / natural-knot interpolation of
 * `ezdxf.math.fit_points_to_cad_cv`. mlightcad discards the fit points during
 * parsing, so this module reads them back out of the DXF bytes and rebuilds the
 * curve the way the reference implementation does.
 *
 * Everything here is pure arithmetic over plain records — no mlightcad import,
 * no DOM — so it runs in vitest, in the renderer and in the desktop main
 * process alike.
 *
 * Algorithms follow ezdxf 1.4.4 (`ezdxf/math/_bspline.py`, `bspline.py`,
 * `parametrize.py`, `construct3d.py`) statement by statement, because matching
 * its *numbers* — not merely being correct NURBS code — is the contract:
 *
 * | this module              | ezdxf                                |
 * |-------------------------|--------------------------------------|
 * | `findSpan`              | `Basis.find_span`                    |
 * | `basisFuncs`            | `Basis.basis_funcs` (NURBS book A2.2)|
 * | `basisVector`           | `Basis.basis_vector`                 |
 * | `evaluateNurbs`         | `Evaluator.point` (A3.1)             |
 * | `flattenNurbs`          | `BSpline.flattening(d, segments=4)`  |
 * | `nurbsLength`           | `stats.py::_flattened_length`        |
 * | `cadFitPointCurve`      | `cad_fit_point_interpolation` / `global_bspline_interpolation_end_tangents` |
 * | `scanSplineFitData`     | the DXF reader's group 11/12/13 pass |
 */

/** Plain 3D point. Deliberately not `Vec3` from `surface-types` to keep this file standalone. */
export interface Point3 {
  x: number;
  y: number;
  z: number;
}

/** A (possibly rational) B-spline curve in the form the DXF SPLINE record stores it. */
export interface NurbsCurve {
  degree: number;
  controlPoints: Point3[];
  /** Full knot vector, `controlPoints.length + degree + 1` values. */
  knots: number[];
  /** Per-control-point weights; omitted or all-ones means a non-rational curve. */
  weights?: number[];
}

/** What {@link scanSplineFitData} recovers for one fit-point SPLINE. */
export interface SplineFitData {
  /** DXF group 11/21/31. */
  fitPoints: Point3[];
  /** DXF group 12/22/32, only when the record carries one. */
  startTangent?: Point3;
  /** DXF group 13/23/33. */
  endTangent?: Point3;
  /** DXF group 71 as written; the reference implementation forces degree 3 anyway. */
  declaredDegree: number;
  /** DXF group 70 bit 0. */
  closed: boolean;
}

/**
 * `ezdxf.math.Vec3.isclose` default tolerance and the one `Evaluator.point`
 * uses to snap the parameter onto `max_t`.
 */
const ABS_TOL = 1e-12;

/** `docs/contracts/stats-definition.md`: "스플라인은 `flattening(0.01)`급 근사". */
export const FLATTEN_DISTANCE_MM = 0.01;

/** `BSpline.flattening`'s `segments` default: minimum segment count between two knots. */
const FLATTEN_SEGMENTS = 4;

function point(x: number, y: number, z: number): Point3 {
  return { x, y, z };
}

function distance(a: Point3, b: Point3): number {
  return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
}

/**
 * Normal distance from `p` to the infinite line through `a` and `b`
 * (`ezdxf.math.distance_point_line_3d`). Returns 0 for a degenerate segment,
 * which is where ezdxf raises `ZeroDivisionError` and `flattening` treats the
 * distance as 0 — same outcome, no exception.
 */
function distancePointLine(p: Point3, a: Point3, b: Point3): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const dz = b.z - a.z;
  const lengthSquared = dx * dx + dy * dy + dz * dz;
  if (lengthSquared === 0) return 0;
  const vx = p.x - a.x;
  const vy = p.y - a.y;
  const vz = p.z - a.z;
  const dot = vx * dx + vy * dy + vz * dz;
  // (end - start).project(v1) has magnitude |dot| / |b - a|
  const projectionSquared = (dot * dot) / lengthSquared;
  const diff = vx * vx + vy * vy + vz * vz - projectionSquared;
  return diff <= 0 ? 0 : Math.sqrt(diff);
}

// ---------------------------------------------------------------------------
// basis functions
// ---------------------------------------------------------------------------

/**
 * `Basis.find_span`. `count` is the number of control points (`n + 1` in the
 * NURBS book). A linear scan is used for the unclamped case for the same
 * reason ezdxf gives: a binary search loops forever on some weird knot
 * vectors found in the wild.
 */
function findSpan(knots: number[], count: number, order: number, u: number): number {
  if (u >= (knots[count] ?? Number.POSITIVE_INFINITY)) return count - 1;
  const degree = order - 1;
  if (knots[degree] === 0) {
    // bisect_right(knots, u, degree, count) - 1
    let low = degree;
    let high = count;
    while (low < high) {
      const mid = (low + high) >>> 1;
      if (u < (knots[mid] ?? 0)) high = mid;
      else low = mid + 1;
    }
    return low - 1;
  }
  let span = 0;
  while (span < count && (knots[span] ?? Number.POSITIVE_INFINITY) <= u) span += 1;
  return span - 1;
}

/** `Basis.basis_funcs` — The NURBS Book, algorithm A2.2, plus `span_weighting`. */
function basisFuncs(
  knots: number[],
  order: number,
  span: number,
  u: number,
  weights: number[] | undefined
): number[] {
  const values = new Array<number>(order).fill(0);
  const left = new Array<number>(order).fill(0);
  const right = new Array<number>(order).fill(0);
  values[0] = 1;
  for (let j = 1; j < order; j += 1) {
    left[j] = u - (knots[Math.max(0, span + 1 - j)] ?? 0);
    right[j] = (knots[span + j] ?? 0) - u;
    let saved = 0;
    for (let r = 0; r < j; r += 1) {
      const temp = (values[r] ?? 0) / ((right[r + 1] ?? 0) + (left[j - r] ?? 0));
      values[r] = saved + (right[r + 1] ?? 0) * temp;
      saved = (left[j - r] ?? 0) * temp;
    }
    values[j] = saved;
  }
  if (!weights) return values;
  const slice = weights.slice(span - order + 1, span + 1);
  if (slice.length !== values.length) return values;
  const products = values.map((value, index) => value * (slice[index] ?? 1));
  const sum = products.reduce((accumulator, value) => accumulator + value, 0);
  return sum === 0 ? values : products.map((value) => value / sum);
}

/** `Basis.basis_vector`: the basis functions padded out to one row of the full system. */
function basisVector(knots: number[], order: number, count: number, u: number): number[] {
  const span = findSpan(knots, count, order, u);
  const degree = order - 1;
  const row = new Array<number>(count).fill(0);
  const funcs = basisFuncs(knots, order, span, u, undefined);
  for (let index = 0; index <= degree; index += 1) {
    row[span - degree + index] = funcs[index] ?? 0;
  }
  return row;
}

/** A clamped ("open uniform") knot vector, used when the file supplies none. */
export function clampedUniformKnots(count: number, order: number): number[] {
  const knots: number[] = [];
  const interior = count - order;
  for (let index = 0; index < order; index += 1) knots.push(0);
  for (let index = 1; index <= interior; index += 1) knots.push(index / (interior + 1));
  for (let index = 0; index < order; index += 1) knots.push(1);
  return knots;
}

/** `Evaluator.point` — The NURBS Book, algorithm A3.1. */
export function evaluateNurbs(curve: NurbsCurve, parameter: number): Point3 {
  const order = curve.degree + 1;
  const count = curve.controlPoints.length;
  const knots = curve.knots;
  const maxT = knots[knots.length - 1] ?? 1;
  let u = parameter;
  if (Math.abs(u - maxT) <= ABS_TOL + 1e-9 * Math.abs(maxT)) u = maxT;
  const span = findSpan(knots, count, order, u);
  const funcs = basisFuncs(knots, order, span, u, curve.weights);
  let x = 0;
  let y = 0;
  let z = 0;
  for (let index = 0; index <= curve.degree; index += 1) {
    const control = curve.controlPoints[span - curve.degree + index];
    const factor = funcs[index] ?? 0;
    if (!control) continue;
    x += factor * control.x;
    y += factor * control.y;
    z += factor * control.z;
  }
  return point(x, y, z);
}

/** Sorted unique knot values — `np.unique(self.knots())` in `BSpline.flattening`. */
function uniqueKnots(knots: number[]): number[] {
  const sorted = [...knots].sort((left, right) => left - right);
  const out: number[] = [];
  for (const value of sorted) {
    if (out.length === 0 || out[out.length - 1] !== value) out.push(value);
  }
  return out;
}

/**
 * `BSpline.flattening(distance, segments)`: every knot interval is split into
 * `segments` pieces, then each piece is bisected while the mid-point of the
 * curve is further than `distance` from its chord.
 *
 * ezdxf recurses; this uses an explicit stack so a pathological curve cannot
 * blow the JS call stack (the emitted point order is identical).
 */
export function flattenNurbs(
  curve: NurbsCurve,
  maxDistance: number = FLATTEN_DISTANCE_MM,
  segments: number = FLATTEN_SEGMENTS
): Point3[] {
  const knots = uniqueKnots(curve.knots);
  const first = knots[0];
  if (first === undefined) return [];
  let t = first;
  let startPoint = evaluateNurbs(curve, t);
  const out: Point3[] = [startPoint];

  for (let index = 1; index < knots.length; index += 1) {
    const t1 = knots[index];
    if (t1 === undefined) continue;
    const delta = (t1 - t) / segments;
    if (delta <= 0) continue;
    while (t < t1) {
      let nextT = t + delta;
      // `np.isclose(next_t, t1)`: rtol 1e-5, atol 1e-8.
      if (Math.abs(nextT - t1) <= 1e-8 + 1e-5 * Math.abs(t1)) nextT = t1;
      const endPoint = evaluateNurbs(curve, nextT);
      subdivide(curve, startPoint, endPoint, t, nextT, maxDistance, out);
      t = nextT;
      startPoint = endPoint;
    }
  }
  return out;
}

/** Iterative twin of ezdxf's `subdiv()` generator; appends to `out` in curve order. */
function subdivide(
  curve: NurbsCurve,
  start: Point3,
  end: Point3,
  startT: number,
  endT: number,
  maxDistance: number,
  out: Point3[]
): void {
  // Depth-first, left branch first, so the stack is filled in reverse.
  const stack: { s: Point3; e: Point3; st: number; et: number }[] = [
    { s: start, e: end, st: startT, et: endT },
  ];
  while (stack.length > 0) {
    const item = stack.pop();
    if (!item) break;
    const midT = (item.st + item.et) * 0.5;
    const mid = evaluateNurbs(curve, midT);
    if (distancePointLine(mid, item.s, item.e) < maxDistance) {
      out.push(item.e);
      continue;
    }
    stack.push({ s: mid, e: item.e, st: midT, et: item.et });
    stack.push({ s: item.s, e: mid, st: item.st, et: midT });
  }
}

/**
 * Length of a NURBS curve, summed over the flattened polyline — the same
 * definition `engine/src/halo_engine/ingest/stats.py::_flattened_length` uses.
 */
export function nurbsLength(curve: NurbsCurve, maxDistance: number = FLATTEN_DISTANCE_MM): number {
  if (curve.controlPoints.length < 2) return 0;
  const points = flattenNurbs(curve, maxDistance);
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    if (a && b) total += distance(a, b);
  }
  return total;
}

/**
 * Normalises a SPLINE record's raw fields into a curve that can be evaluated.
 * A knot vector of the wrong length is replaced by a clamped uniform one rather
 * than throwing: a viewer must still measure a slightly broken drawing.
 */
export function nurbsFromControlPoints(spec: {
  degree: number;
  controlPoints: Point3[];
  knots: number[];
  weights?: number[];
}): NurbsCurve | null {
  const count = spec.controlPoints.length;
  if (count < 2) return null;
  const degree = Math.min(Math.max(1, spec.degree), count - 1);
  const order = degree + 1;
  const knots =
    spec.knots.length === count + order ? [...spec.knots] : clampedUniformKnots(count, order);
  const weights =
    spec.weights && spec.weights.length === count && spec.weights.some((value) => value !== 1)
      ? [...spec.weights]
      : undefined;
  return { degree, controlPoints: spec.controlPoints, knots, ...(weights ? { weights } : {}) };
}

// ---------------------------------------------------------------------------
// fit point interpolation
// ---------------------------------------------------------------------------

/** `create_t_vector(points, "chord")` — cumulative chord length, normalised to [0, 1]. */
function chordParameters(points: Point3[]): number[] {
  const distances: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const a = points[index - 1];
    const b = points[index];
    distances.push(a && b ? distance(a, b) : 0);
  }
  const total = distances.reduce((accumulator, value) => accumulator + value, 0);
  if (Math.abs(total) <= 1e-12) return [];
  const parameters = [0];
  let running = 0;
  for (let index = 0; index < distances.length - 1; index += 1) {
    running += distances[index] ?? 0;
    parameters.push(running / total);
  }
  parameters.push(1);
  return parameters;
}

/** `natural_knots_constrained(n, p, t)` with `n = count of control points - 1`. */
function naturalKnotsConstrained(n: number, degree: number, t: number[]): number[] {
  const knots = new Array<number>(degree + 1).fill(0);
  knots.push(...t.slice(1, n - degree + 1));
  for (let index = 0; index <= degree; index += 1) knots.push(1);
  return knots;
}

/**
 * Solves `matrix * X = rhs` for 3D right-hand sides by Gaussian elimination
 * with partial pivoting. ezdxf picks a banded/LU solver here; for the system
 * sizes a SPLINE produces (fit points + 2) the numerical result is the same and
 * this stays dependency-free.
 */
function solve(matrix: number[][], rhs: Point3[]): Point3[] | null {
  const size = matrix.length;
  const a = matrix.map((row) => [...row]);
  const b = rhs.map((value) => [value.x, value.y, value.z]);
  for (let column = 0; column < size; column += 1) {
    let pivot = column;
    let best = Math.abs(a[column]?.[column] ?? 0);
    for (let row = column + 1; row < size; row += 1) {
      const candidate = Math.abs(a[row]?.[column] ?? 0);
      if (candidate > best) {
        best = candidate;
        pivot = row;
      }
    }
    if (best < 1e-14) return null;
    if (pivot !== column) {
      const rowA = a[column];
      const rowB = a[pivot];
      const rhsA = b[column];
      const rhsB = b[pivot];
      if (!rowA || !rowB || !rhsA || !rhsB) return null;
      a[column] = rowB;
      a[pivot] = rowA;
      b[column] = rhsB;
      b[pivot] = rhsA;
    }
    const pivotRow = a[column];
    const pivotRhs = b[column];
    const pivotValue = pivotRow?.[column];
    if (!pivotRow || !pivotRhs || pivotValue === undefined) return null;
    for (let row = column + 1; row < size; row += 1) {
      const currentRow = a[row];
      const currentRhs = b[row];
      if (!currentRow || !currentRhs) continue;
      const factor = (currentRow[column] ?? 0) / pivotValue;
      if (factor === 0) continue;
      for (let index = column; index < size; index += 1) {
        currentRow[index] = (currentRow[index] ?? 0) - factor * (pivotRow[index] ?? 0);
      }
      for (let index = 0; index < 3; index += 1) {
        currentRhs[index] = (currentRhs[index] ?? 0) - factor * (pivotRhs[index] ?? 0);
      }
    }
  }
  const solution: Point3[] = new Array<Point3>(size);
  for (let row = size - 1; row >= 0; row -= 1) {
    const currentRow = a[row];
    const currentRhs = b[row];
    const diagonal = currentRow?.[row];
    if (!currentRow || !currentRhs || diagonal === undefined) return null;
    const accumulator = [currentRhs[0] ?? 0, currentRhs[1] ?? 0, currentRhs[2] ?? 0];
    for (let column = row + 1; column < size; column += 1) {
      const known = solution[column];
      const coefficient = currentRow[column] ?? 0;
      if (!known || coefficient === 0) continue;
      accumulator[0] = (accumulator[0] ?? 0) - coefficient * known.x;
      accumulator[1] = (accumulator[1] ?? 0) - coefficient * known.y;
      accumulator[2] = (accumulator[2] ?? 0) - coefficient * known.z;
    }
    solution[row] = point(
      (accumulator[0] ?? 0) / diagonal,
      (accumulator[1] ?? 0) / diagonal,
      (accumulator[2] ?? 0) / diagonal
    );
  }
  return solution;
}

function scale(vector: Point3, factor: number): Point3 {
  return point(vector.x * factor, vector.y * factor, vector.z * factor);
}

function normalise(vector: Point3, magnitude: number): Point3 | null {
  const length = Math.hypot(vector.x, vector.y, vector.z);
  if (length === 0) return null;
  return scale(vector, magnitude / length);
}

/**
 * `cad_fit_point_interpolation` — global cubic interpolation with chord
 * parametrisation, natural knots and `C''(0) == C''(1) == 0`. This is the
 * curve AutoCAD and BricsCAD build from fit points, and therefore the one the
 * engine measures.
 */
function cadFitPointInterpolation(fitPoints: Point3[]): NurbsCurve | null {
  const t = chordParameters(fitPoints);
  if (t.length !== fitPoints.length) return null;
  const n = fitPoints.length - 1;
  const degree = 3;
  const count = n + 3;
  const knots = naturalKnotsConstrained(n + 2, degree, t);
  if (knots.length !== count + degree + 1) return null;

  const up1 = knots[degree + 1] ?? 0;
  const up2 = knots[degree + 2] ?? 0;
  const last = knots.length - 1;
  const ump1 = knots[last - degree - 1] ?? 1;
  const ump2 = knots[last - degree - 2] ?? 1;
  if (up1 === 0 || up2 === 0 || ump1 === 1 || ump2 === 1) return null;

  const f1 = (degree * (degree - 1)) / up1;
  const coefficients1 = [f1 / up1, (-f1 * (up1 + up2)) / (up1 * up2), f1 / up2];
  const f2 = (degree * (degree - 1)) / (1 - ump1);
  const coefficients2 = [
    f2 / (1 - ump2),
    (-f2 * (2 - ump1 - ump2)) / (1 - ump1) / (1 - ump2),
    f2 / (1 - ump1),
  ];

  const spacing = new Array<number>(n).fill(0);
  const rows = t.map((parameter) => basisVector(knots, degree + 1, count, parameter));
  rows.splice(1, 0, [...coefficients1, ...spacing]);
  rows.splice(rows.length - 1, 0, [...spacing, ...coefficients2]);

  const rhs = [...fitPoints];
  rhs.splice(1, 0, point(0, 0, 0));
  rhs.splice(rhs.length - 1, 0, point(0, 0, 0));

  const controlPoints = solve(rows, rhs);
  if (!controlPoints) return null;
  return { degree, controlPoints, knots };
}

/**
 * `global_bspline_interpolation_end_tangents` — the branch ezdxf takes when the
 * SPLINE record carries both a start and an end tangent (groups 12 and 13).
 */
function fitPointInterpolationWithTangents(
  fitPoints: Point3[],
  startTangent: Point3,
  endTangent: Point3
): NurbsCurve | null {
  const t = chordParameters(fitPoints);
  if (t.length !== fitPoints.length) return null;
  // estimate_end_tangent_magnitude(points, method="chord")
  let chordTotal = 0;
  for (let index = 1; index < fitPoints.length; index += 1) {
    const a = fitPoints[index - 1];
    const b = fitPoints[index];
    if (a && b) chordTotal += distance(a, b);
  }
  const start = normalise(startTangent, chordTotal);
  const end = normalise(endTangent, chordTotal);
  if (!start || !end) return cadFitPointInterpolation(fitPoints);

  const n = fitPoints.length - 1;
  const degree = 3;
  const count = n + 3;
  const knots = naturalKnotsConstrained(n + 2, degree, t);
  if (knots.length !== count + degree + 1) return null;

  const spacing = new Array<number>(n + 1).fill(0);
  const rows = t.map((parameter) => basisVector(knots, degree + 1, count, parameter));
  rows.splice(1, 0, [-1, 1, ...spacing]);
  rows.splice(rows.length - 1, 0, [...spacing, -1, 1]);

  const rhs = [...fitPoints];
  rhs.splice(1, 0, scale(start, (knots[degree + 1] ?? 0) / degree));
  rhs.splice(rhs.length - 1, 0, scale(end, (1 - (knots[knots.length - degree - 2] ?? 1)) / degree));

  const controlPoints = solve(rows, rhs);
  if (!controlPoints) return null;
  return { degree, controlPoints, knots };
}

/**
 * `fit_points_to_cad_cv(fit_points, tangents)`: the cubic B-spline AutoCAD /
 * BricsCAD / ezdxf build from a SPLINE's fit points. Returns `null` when the
 * data cannot produce a curve (fewer than two distinct points, singular
 * system) so the caller can fall back to whatever the parser reconstructed.
 */
export function cadFitPointCurve(fit: SplineFitData): NurbsCurve | null {
  const points = fit.fitPoints;
  if (points.length < 2) return null;
  if (fit.startTangent && fit.endTangent) {
    return fitPointInterpolationWithTangents(points, fit.startTangent, fit.endTangent);
  }
  return cadFitPointInterpolation(points);
}

/** Length of a fit-point SPLINE the way the engine measures it, or `null`. */
export function fitPointSplineLength(
  fit: SplineFitData,
  maxDistance: number = FLATTEN_DISTANCE_MM
): number | null {
  const curve = cadFitPointCurve(fit);
  return curve === null ? null : nurbsLength(curve, maxDistance);
}

// ---------------------------------------------------------------------------
// DXF source scan
// ---------------------------------------------------------------------------

const BINARY_DXF_SENTINEL = 'AutoCAD Binary DXF';

/**
 * Recovers the fit points of every fit-point SPLINE in a DXF, keyed by handle
 * (DXF group 5, upper case).
 *
 * Why a second pass over the bytes instead of asking the parser: data-model
 * 1.14.3 turns a fit-point SPLINE into a control-point spline while reading
 * (`AcDbSpline.fromDwgSpline` → `fromFitPoints`) and keeps neither the fit
 * points nor a flag saying it did — measured on `fixtures/generated/F01.dxf`,
 * where `_geo.fitPoints` is `[]` and `isFitPointSpline` is `false`. The DXF
 * bytes are the only remaining source, and they are the same bytes the engine
 * reads (ADR-0002 §2), so both sides interpolate from identical input.
 *
 * The scan walks group code / value line pairs and never materialises the whole
 * file as a string: only the handful of value lines belonging to a SPLINE are
 * decoded. Binary DXF and anything that does not parse as line pairs yields an
 * empty map, which degrades to the parser's own geometry.
 */
export function scanSplineFitData(bytes: ArrayBuffer): Map<string, SplineFitData> {
  const out = new Map<string, SplineFitData>();
  const view = new Uint8Array(bytes);
  if (view.length === 0) return out;
  let head = '';
  for (let index = 0; index < Math.min(view.length, BINARY_DXF_SENTINEL.length); index += 1) {
    head += String.fromCharCode(view[index] ?? 0);
  }
  if (head === BINARY_DXF_SENTINEL) return out;

  let cursor = 0;
  let inSpline = false;
  let handle: string | null = null;
  let numberOfControlPoints = 0;
  let numberOfFitPoints = 0;
  let declaredDegree = 3;
  let closed = false;
  const fitCoordinates: number[][] = [[], [], []];
  const startTangent: number[] = [];
  const endTangent: number[] = [];

  const flush = (): void => {
    if (
      inSpline &&
      handle !== null &&
      numberOfControlPoints === 0 &&
      numberOfFitPoints >= 2 &&
      (fitCoordinates[0]?.length ?? 0) >= 2
    ) {
      const xs = fitCoordinates[0] ?? [];
      const ys = fitCoordinates[1] ?? [];
      const zs = fitCoordinates[2] ?? [];
      const fitPoints: Point3[] = xs.map((x, index) =>
        point(x, ys[index] ?? 0, zs[index] ?? 0)
      );
      const record: SplineFitData = { fitPoints, declaredDegree, closed };
      if (startTangent.length >= 2) {
        record.startTangent = point(
          startTangent[0] ?? 0,
          startTangent[1] ?? 0,
          startTangent[2] ?? 0
        );
      }
      if (endTangent.length >= 2) {
        record.endTangent = point(endTangent[0] ?? 0, endTangent[1] ?? 0, endTangent[2] ?? 0);
      }
      out.set(handle.toUpperCase(), record);
    }
    inSpline = false;
    handle = null;
    numberOfControlPoints = 0;
    numberOfFitPoints = 0;
    declaredDegree = 3;
    closed = false;
    fitCoordinates[0] = [];
    fitCoordinates[1] = [];
    fitCoordinates[2] = [];
    startTangent.length = 0;
    endTangent.length = 0;
  };

  const readLine = (): { start: number; end: number } | null => {
    if (cursor >= view.length) return null;
    const start = cursor;
    let end = cursor;
    while (end < view.length && view[end] !== 0x0a) end += 1;
    cursor = end + 1;
    if (end > start && view[end - 1] === 0x0d) end -= 1;
    return { start, end };
  };

  const asString = (span: { start: number; end: number }): string => {
    let text = '';
    for (let index = span.start; index < span.end; index += 1) {
      text += String.fromCharCode(view[index] ?? 0);
    }
    return text.trim();
  };

  const asInteger = (span: { start: number; end: number }): number => {
    let value = 0;
    let sign = 1;
    let seen = false;
    for (let index = span.start; index < span.end; index += 1) {
      const byte = view[index] ?? 0;
      if (byte === 0x20 || byte === 0x09) {
        if (seen) break;
        continue;
      }
      if (byte === 0x2d && !seen) {
        sign = -1;
        seen = true;
        continue;
      }
      if (byte < 0x30 || byte > 0x39) return Number.NaN;
      value = value * 10 + (byte - 0x30);
      seen = true;
    }
    return seen ? sign * value : Number.NaN;
  };

  for (;;) {
    const codeSpan = readLine();
    if (!codeSpan) break;
    const valueSpan = readLine();
    if (!valueSpan) break;
    const code = asInteger(codeSpan);
    if (Number.isNaN(code)) continue;

    if (code === 0) {
      const type = asString(valueSpan);
      flush();
      if (type === 'SPLINE') inSpline = true;
      continue;
    }
    if (!inSpline) continue;

    switch (code) {
      case 5:
        handle ??= asString(valueSpan);
        break;
      case 70:
        closed = (asInteger(valueSpan) & 1) === 1;
        break;
      case 71: {
        const value = asInteger(valueSpan);
        if (!Number.isNaN(value)) declaredDegree = value;
        break;
      }
      case 73:
        numberOfControlPoints = asInteger(valueSpan) || 0;
        break;
      case 74:
        numberOfFitPoints = asInteger(valueSpan) || 0;
        break;
      case 11:
      case 21:
      case 31: {
        const axis = (code - 11) / 10;
        const value = Number.parseFloat(asString(valueSpan));
        if (Number.isFinite(value)) (fitCoordinates[axis] ??= []).push(value);
        break;
      }
      case 12:
      case 22:
      case 32:
        startTangent[(code - 12) / 10] = Number.parseFloat(asString(valueSpan));
        break;
      case 13:
      case 23:
      case 33:
        endTangent[(code - 13) / 10] = Number.parseFloat(asString(valueSpan));
        break;
      default:
        break;
    }
  }
  flush();
  return out;
}
