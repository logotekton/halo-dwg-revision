import { BoundaryPathFlags, type Hatch } from "@node-projects/acad-ts";

/**
 * `hatch_area_sum_mm2`: net signed sum of every boundary path's polygon area
 * -- external/outermost paths add, other (hole/island) paths subtract.
 * Matches fixtures_gen's ezdxf-side truth exactly (`_hatch_area` in
 * fixtures/gen/src/fixtures_gen/stats.py): a path is a hole when neither the
 * `External` (1) nor `Outermost` (16) flag bit is set, i.e.
 * `flags & 0b10001 === 0`. `HatchBoundaryPath.getPoints()` flattens arcs,
 * ellipses and splines on edge-based paths too (256-segment default), but
 * every HATCH boundary in fixtures/generated is a straight-edge
 * `PolylinePath` (bulge 0), so the shoelace result is exact for those.
 */
const EXTERNAL_OR_OUTERMOST = BoundaryPathFlags.External | BoundaryPathFlags.Outermost;

function shoelaceArea(points: readonly { x: number; y: number }[]): number {
  const n = points.length;
  if (n < 3) return 0;
  let acc = 0;
  for (let i = 0; i < n; i++) {
    const p1 = points[i];
    const p2 = points[(i + 1) % n];
    if (!p1 || !p2) continue;
    acc += p1.x * p2.y - p2.x * p1.y;
  }
  return Math.abs(acc) / 2;
}

export function hatchArea(hatch: Hatch): number {
  let total = 0;
  for (const path of hatch.paths) {
    const points = path.getPoints();
    const area = shoelaceArea(points);
    const isHole = (path.flags & EXTERNAL_OR_OUTERMOST) === 0;
    total += isHole ? -area : area;
  }
  return total;
}
