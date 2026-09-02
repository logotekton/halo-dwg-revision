"""Shared LINE+TEXT table drawing helper, used by F07 (member schedules) and
F08 (level table). DXF has no first-class table entity used here on purpose
-- see ``docs/briefs/W1-03.md`` "Reference implementation": tables are
LINE grid + TEXT, matching Korean drawing practice, not ACAD_TABLE.
"""

from __future__ import annotations

from ezdxf.enums import TextEntityAlignment


def draw_table(
    msp,
    origin: tuple[float, float],
    col_widths: list[float],
    headers: list[str],
    rows: list[list[str]],
    merges: list[tuple[int, int, int]],
    title: str,
    layer_grid: str,
    layer_text: str,
    row_height: float = 300.0,
    text_height: float = 120.0,
) -> dict:
    """Draw one LINE+TEXT table. ``merges``: list of (row_start, row_end, col),
    0-indexed *including* the header row at index 0, inclusive range, meaning
    that column's cell spans rows [row_start, row_end] and only carries text
    once (at row_start); the internal horizontal boundary is not drawn.

    Returns the truth dict: column boundaries, row boundaries, cell matrix
    (merged cells repeat their anchor's value), and the merge list.
    """
    all_rows = [headers, *rows]
    n_rows = len(all_rows)
    n_cols = len(col_widths)

    col_x = [origin[0]]
    for w in col_widths:
        col_x.append(col_x[-1] + w)
    row_y = [origin[1]]
    for _ in range(n_rows):
        row_y.append(row_y[-1] - row_height)

    # Two distinct sets, deliberately not conflated:
    #  * `skip_boundary_below[r, c]` -- the horizontal grid segment strictly
    #    between row r and row r+1, for column c, must not be drawn.
    #  * `covered_cells` -- cells hidden inside a merge (every row of the
    #    merge except its anchor row); they get no TEXT of their own.
    skip_boundary_below: set[tuple[int, int]] = set()
    covered_cells: set[tuple[int, int]] = set()
    merge_anchor: dict[tuple[int, int], int] = {}  # (anchor_row, col) -> row_end
    for row_start, row_end, col in merges:
        merge_anchor[(row_start, col)] = row_end
        for r in range(row_start, row_end):
            skip_boundary_below.add((r, col))
        for r in range(row_start + 1, row_end + 1):
            covered_cells.add((r, col))

    # vertical lines: full height, one per column boundary (no column merges)
    for c in range(n_cols + 1):
        msp.add_line((col_x[c], row_y[0]), (col_x[c], row_y[-1]), dxfattribs={"layer": layer_grid})

    # horizontal lines: per-column segment, skipped where suppressed by a merge
    for r in range(n_rows + 1):
        for c in range(n_cols):
            if (r - 1, c) in skip_boundary_below and r != 0 and r != n_rows:
                continue
            msp.add_line(
                (col_x[c], row_y[r]), (col_x[c + 1], row_y[r]), dxfattribs={"layer": layer_grid}
            )

    # title above the table
    msp.add_text(
        title, dxfattribs={"layer": layer_text, "height": text_height * 1.3}
    ).set_placement((col_x[0], row_y[0] + text_height * 1.6))

    cell_matrix: list[list[str]] = [list(row) for row in all_rows]
    for r in range(n_rows):
        for c in range(n_cols):
            if (r, c) in covered_cells:
                continue  # covered by a merge anchored at an earlier row
            text = all_rows[r][c]
            row_span_end = merge_anchor.get((r, c), r)
            cy = (row_y[r] + row_y[row_span_end + 1]) / 2
            cx = (col_x[c] + col_x[c + 1]) / 2
            if text:
                msp.add_text(
                    text, dxfattribs={"layer": layer_text, "height": text_height}
                ).set_placement((cx, cy), align=TextEntityAlignment.MIDDLE_CENTER)

    # truth cell_matrix repeats the anchor's value into cells it covers, so
    # a consumer can index [row][col] without knowing about merges.
    for row_start, row_end, col in merges:
        for r in range(row_start + 1, row_end + 1):
            cell_matrix[r][col] = cell_matrix[row_start][col]

    return {
        "title": title,
        "col_boundaries_x": col_x,
        "row_boundaries_y": row_y,
        "headers": headers,
        "cell_matrix": cell_matrix,
        "merges": [{"row_start": rs, "row_end": re, "col": c} for rs, re, c in merges],
    }
