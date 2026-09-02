"""F09 gap verification: the two intentional 150mm wall gaps recorded in
truth["extra"]["gaps"] must be real breaks in the generated wall geometry --
independently re-derived from the DXF, not merely echoed from the generator.
"""

from __future__ import annotations

import json
import math

import ezdxf

from fixtures_gen.fixtures.f09_rooms import WALL_THICKNESS


def test_f09_gap_count_and_width(truth_dir) -> None:
    truth = json.loads((truth_dir / "F09.json").read_text(encoding="utf-8"))
    gaps = truth["extra"]["gaps"]
    assert len(gaps) == 2
    for g in gaps:
        assert g["width"] == truth["extra"]["gap_width_mm"] == 150.0


def test_f09_gaps_are_real_breaks_in_geometry(generated_dir, truth_dir) -> None:
    truth = json.loads((truth_dir / "F09.json").read_text(encoding="utf-8"))
    gaps = truth["extra"]["gaps"]
    doc = ezdxf.readfile(str(generated_dir / "F09.dxf"))
    wall_lines = [e for e in doc.modelspace().query("LINE") if e.dxf.layer == "A-WALL"]

    # the wall is drawn as two parallel offset lines +/- half the wall
    # thickness from the centerline (see f09_rooms._draw_wall), so a line
    # "at" the gap's centerline x sits within half-thickness of it, not on it.
    near_wall = WALL_THICKNESS / 2 + 1.0

    for gap in gaps:
        gx, gy = gap["center"]
        half_width = gap["width"] / 2

        # A vertical wall gap: no A-WALL line's y-range should straddle the
        # gap's y interval at x close to the wall's x position (the gap's x).
        crossing = []
        for e in wall_lines:
            x1, y1 = e.dxf.start.x, e.dxf.start.y
            x2, y2 = e.dxf.end.x, e.dxf.end.y
            same_x = math.isclose(x1, x2, abs_tol=1e-6) and abs(x1 - gx) <= near_wall
            if not same_x:
                continue
            lo, hi = sorted((y1, y2))
            # a line "straddles" the gap if it covers past the gap center on
            # both sides -- i.e. the gap gets no coverage at all, but a real
            # break means no line covers [gy - half_width, gy + half_width].
            if lo <= gy - half_width and hi >= gy + half_width:
                crossing.append(e.dxf.handle)

        assert crossing == [], (
            f"gap {gap['tag']} at {gap['center']} is NOT a real break: "
            f"line(s) {crossing} span across it uninterrupted"
        )

        # and confirm the wall really is broken there: at least one segment
        # should end within [gy - half_width, gy + half_width] on each side.
        endpoints_in_gap = [
            e.dxf.handle
            for e in wall_lines
            if abs(e.dxf.start.x - gx) <= near_wall
            and (
                gy - half_width - 1e-6 <= e.dxf.start.y <= gy + half_width + 1e-6
                or gy - half_width - 1e-6 <= e.dxf.end.y <= gy + half_width + 1e-6
            )
        ]
        assert len(endpoints_in_gap) >= 2, (
            f"gap {gap['tag']}: expected wall segments ending at both edges of the gap, "
            f"found {endpoints_in_gap}"
        )
