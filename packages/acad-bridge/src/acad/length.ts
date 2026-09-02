import {
  Arc,
  Circle,
  Ellipse,
  Entity,
  Line,
  LwPolyline,
  Polyline2D,
  Polyline3D,
  Spline,
  Vertex2D,
  type XYZ,
} from "@node-projects/acad-ts";

/**
 * `length_sum_mm` per docs/contracts/stats-definition.md: "LINE, LWPOLYLINE,
 * POLYLINE(2D), ARC, CIRCLE, ELLIPSE, SPLINE의 길이 합(mm). 벌지는 해석식,
 * 스플라인은 flattening(0.01)급 근사." LINE/CIRCLE/ARC/bulge segments use
 * closed-form geometry (matches fixtures_gen's ezdxf-side truth computation
 * exactly, see fixtures/gen/src/fixtures_gen/stats.py `_entity_length` /
 * `_polyline_length`). SPLINE and ELLIPSE have no closed form here, so they
 * are flattened via acad-ts's own `polygonalVertexes(precision)` -- the
 * brief's fallback ("자체 구현... 스플라인은 제어점 폴리라인 근사") only
 * applies when acad-ts has no geometry utility; it has one, and a proper
 * curve flattening is strictly better than connecting raw control points.
 */

function dist3(a: XYZ, b: XYZ): number {
  return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
}

function dist2(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(b.x - a.x, b.y - a.y);
}

/** DXF bulge convention: `4 * atan(bulge)` is the arc's included angle. */
function bulgeSegmentLength(a: { x: number; y: number }, b: { x: number; y: number }, bulge: number): number {
  const chord = dist2(a, b);
  if (bulge) {
    const angle = 4 * Math.atan(bulge);
    if (angle) {
      const radius = Math.abs(chord / (2 * Math.sin(angle / 2)));
      return radius * Math.abs(angle);
    }
  }
  return chord;
}

interface BulgeVertex {
  x: number;
  y: number;
  bulge: number;
}

function polylineLength(vertices: BulgeVertex[], closed: boolean): number {
  const n = vertices.length;
  if (n < 2) return 0;
  const segCount = closed ? n : n - 1;
  let total = 0;
  for (let i = 0; i < segCount; i++) {
    const a = vertices[i];
    const b = vertices[(i + 1) % n];
    if (!a || !b) continue;
    total += bulgeSegmentLength(a, b, a.bulge);
  }
  return total;
}

function flattenLength(points: XYZ[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    if (!prev || !cur) continue;
    total += dist3(prev, cur);
  }
  return total;
}

/** Uniform-parameter subdivision count for SPLINE/ELLIPSE flattening. */
function flatteningPrecision(controlPointCount: number): number {
  return Math.min(2000, Math.max(200, controlPointCount * 50));
}

export function entityLength(entity: Entity): number {
  // Arc must be checked before Circle: `Arc extends Circle` in acad-ts.
  if (entity instanceof Arc) {
    let span = (entity.endAngle - entity.startAngle) % (Math.PI * 2);
    if (span < 0) span += Math.PI * 2;
    if (span === 0) span = Math.PI * 2;
    return entity.radius * span;
  }
  if (entity instanceof Circle) {
    return 2 * Math.PI * entity.radius;
  }
  if (entity instanceof Line) {
    return dist3(entity.startPoint, entity.endPoint);
  }
  if (entity instanceof LwPolyline) {
    const vertices: BulgeVertex[] = entity.vertices.map((v) => ({
      x: v.location.x,
      y: v.location.y,
      bulge: v.bulge,
    }));
    return polylineLength(vertices, entity.isClosed);
  }
  if (entity instanceof Polyline2D) {
    const vertices: BulgeVertex[] = [];
    for (const v of entity.vertices) {
      if (v instanceof Vertex2D) vertices.push({ x: v.location.x, y: v.location.y, bulge: v.bulge });
    }
    return polylineLength(vertices, entity.isClosed);
  }
  if (entity instanceof Polyline3D) {
    // stats-definition.md says "POLYLINE(2D)" explicitly; old-style 3D
    // polylines are not part of length_sum_mm (see README Decisions).
    return 0;
  }
  if (entity instanceof Ellipse) {
    return flattenLength(entity.polygonalVertexes(flatteningPrecision(4)));
  }
  if (entity instanceof Spline) {
    return flattenLength(entity.polygonalVertexes(flatteningPrecision(entity.controlPoints.length || 4)));
  }
  return 0;
}
