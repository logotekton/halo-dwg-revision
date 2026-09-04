"""마크업 DXF: the 후 drawing with the approved cloud marks and the revision table.

What the site actually receives is not the compare DXF -- that one is a review
aid full of ``__CMP_*`` layers -- but an ordinary drawing that looks like the
one they already have, plus red clouds, numbered triangles and a small table
next to the title block. ``docs/contracts/compare-dxf.md`` §2 states it as an
equation:

    마크업 DWG = 후 작업용 DXF 사본 + ``REV-<날짜>[-n]`` 레이어 + 리비전 표

Three consequences run through this module:

* **A copy, not an extract.** The whole 후 working DXF is opened and written
  back out -- every layer, every entity, including anything outside this 도곽.
  The compare DXF is assembled entity by entity because it must hold one sheet
  and two drawings' blocks; the markup must stay openable in ZWCAD next to the
  original and diffable against it, so nothing is dropped or renamed.
* **The coordinates are the sidecar's, verbatim.** ``clusters.json`` already
  holds the cloud polyline the reviewer approved (``cluster.py`` computed it),
  and this module writes those numbers straight through rather than recomputing
  them. Screen C and the printed drawing must show the same cloud in the same
  place; a rounding difference between the two would be invisible in testing
  and obvious on paper.
* **Only 승인.** 무시 and 대기 clusters are dropped here, and a sheet with no
  approved cluster produces no file at all (contract §6). The revision table's
  rows are exactly the clouds that were drawn, in number order.

Every length comes from ``compare.yaml`` multiplied by the sheet's
``scale_factor`` (contract §5, §6); there are no sizes in this file. The output
is byte-identical for the same inputs and the same ``run_date``
(``pin_header_for_determinism`` + :func:`~halo_engine.compare.compare_dxf.serialize`,
contract §8).
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox as ezdxf_bbox
from ezdxf.document import Drawing

from halo_engine.bundle.guard import assert_writable_path
from halo_engine.compare.cluster import badge_geometry
from halo_engine.compare.compare_dxf import (
    APPID,
    pin_header_for_determinism,
    serialize,
)
from halo_engine.compare.config import CompareConfig, scale_factor
from halo_engine.compare.frames import FrameRecord

logger = logging.getLogger("halo_engine.compare.markup")

#: File name of the intermediate markup drawing inside the bundle
#: (``.halo/compare/<pair_id>/markup.dxf``, contract §1).
MARKUP_DXF_NAME = "markup.dxf"

#: ``cluster.decision`` that gets a cloud mark and a table row.
DECISION_APPROVED = "approved"

#: Cut marker appended to a 내용 that does not fit its column (contract §6).
ELLIPSIS = "…"

#: Advance width of one character as a fraction of the TEXT height. Used *only*
#: to decide where to cut a long 내용 -- ezdxf cannot measure a SHX/TTF string
#: without the font, and the cut has to be deterministic on every machine, so
#: it is estimated: a Korean syllable is drawn full-width, a latin letter about
#: half. Over-estimating trims a character early, which is harmless; the table
#: cell is never overflowed.
WIDE_CHAR_RATIO = 1.0
NARROW_CHAR_RATIO = 0.6

#: Warning codes this module raises (brief Defaults for ambiguity).
WARN_TABLE_OUTSIDE_FRAME = "revtable_outside_frame"
WARN_NO_TITLEBLOCK_BBOX = "titleblock_bbox_unknown"


# --------------------------------------------------------------------------- results


@dataclass(frozen=True)
class RevisionRow:
    """One row of the revision table: an approved cluster, as the table says it."""

    number: int
    """Cluster number -- the same number as the triangle badge on the drawing."""

    content: str
    """``user_label`` if the reviewer typed one, else the automatic ``label``."""


@dataclass
class RevisionTable:
    """Where the table was drawn, in model coordinates. Returned so the export
    (and the tests) can say where it landed without re-deriving the layout."""

    left: float
    right: float
    top: float
    bottom: float
    column_x: list[float] = field(default_factory=list)
    """Vertical grid lines, left to right (``len(columns) + 1`` values)."""

    row_y: list[float] = field(default_factory=list)
    """Horizontal grid lines, top to bottom (header + rows + 1 values)."""

    rows: list[RevisionRow] = field(default_factory=list)


@dataclass
class MarkupResult:
    """What :func:`write_markup_dxf` produced for one 도곽 짝."""

    path: Path
    layer_name: str
    numbers: list[int] = field(default_factory=list)
    """Approved cluster numbers, ascending -- the clouds that were drawn."""

    table: RevisionTable | None = None
    sha256: str = ""
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers


def approved_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The clusters that get drawn, in number order (contract §6).

    ``무시`` and ``대기`` are dropped here rather than by every caller: a cluster
    the reviewer has not approved must not reach a printed drawing, and that
    rule is easier to keep in one place than in three.
    """
    return sorted(
        (cluster for cluster in clusters if cluster.get("decision") == DECISION_APPROVED),
        key=lambda cluster: int(cluster["number"]),
    )


def cluster_content(cluster: dict[str, Any]) -> str:
    """The 내용 column of a cluster: the reviewer's own words, or the automatic label."""
    return str(cluster.get("user_label") or cluster.get("label") or "")


def _set_xdata(entity: Any, cluster_number: int, role: str) -> None:
    """Contract §4: a cloud or a badge carries its cluster number and its role."""
    entity.set_xdata(APPID, [(1000, f"cluster={cluster_number}"), (1000, f"role={role}")])


def _ensure_appid(doc: Drawing) -> None:
    if APPID not in doc.appids:
        doc.appids.add(APPID)


def _ensure_layer(doc: Drawing, layer_name: str, color: int) -> None:
    """The revision layer, colour 1 by ``cloud.color`` (contract §2).

    A drawing that already carries a layer of this name (a re-export onto a
    drawing that was itself an export, say) has its colour corrected rather than
    a second table entry added -- DXF layer names are unique.
    """
    if layer_name in doc.layers:
        doc.layers.get(layer_name).dxf.color = color
        return
    doc.layers.add(layer_name, color=color)


def text_width(text: str, height: float) -> float:
    """Estimated drawn width of ``text`` at ``height`` (see :data:`WIDE_CHAR_RATIO`)."""
    total = 0.0
    for char in text:
        wide = unicodedata.east_asian_width(char) in {"W", "F"}
        total += height * (WIDE_CHAR_RATIO if wide else NARROW_CHAR_RATIO)
    return total


def fit_text(text: str, height: float, available: float) -> str:
    """``text`` cut to ``available`` millimetres, ending in ``…`` when it was cut.

    Contract §6: "긴 내용은 열 너비에 맞춰 잘라 ``…``". A cell that cannot hold
    even one character plus the marker comes back empty rather than overflowing
    into the next column.
    """
    if available <= 0:
        return ""
    if text_width(text, height) <= available:
        return text
    marker_width = text_width(ELLIPSIS, height)
    kept = ""
    for char in text:
        if text_width(kept + char, height) + marker_width > available:
            break
        kept += char
    return f"{kept}{ELLIPSIS}" if kept else ""


def titleblock_bbox(doc: Drawing, frame: FrameRecord) -> tuple[list[float] | None, list[str]]:
    """The title block INSERT's bounding box in world coordinates, or ``None``.

    ``sheet_frame`` stores the title block's *handle*, not its box (contract
    §3), so the box is measured from the drawing the export is writing anyway.
    A frame whose title block cannot be measured (an unrecognised file, a block
    with no geometry) returns ``None`` and the caller falls back -- a missing
    title block must cost the table its position, not the sheet its clouds.
    """
    handle = frame.titleblock_handle
    if not handle:
        return None, [WARN_NO_TITLEBLOCK_BBOX]
    entity = doc.entitydb.get(handle)
    if entity is None:
        return None, [WARN_NO_TITLEBLOCK_BBOX]
    try:
        extents = ezdxf_bbox.extents([entity], fast=False)
    except Exception:  # noqa: BLE001 - a block ezdxf cannot measure is not fatal
        logger.warning("could not measure the title block %s", handle)
        return None, [WARN_NO_TITLEBLOCK_BBOX]
    if not extents.has_data:
        return None, [WARN_NO_TITLEBLOCK_BBOX]
    return (
        [
            float(extents.extmin.x),
            float(extents.extmin.y),
            float(extents.extmax.x),
            float(extents.extmax.y),
        ],
        [],
    )


# --------------------------------------------------------------------------- the table


def draw_revision_table(
    doc: Drawing,
    *,
    frame: FrameRecord,
    rows: list[RevisionRow],
    run_date: str,
    layer_name: str,
    config: CompareConfig,
    factor: float,
) -> tuple[RevisionTable | None, list[str]]:
    """The 번호·내용·일자 table, LINE and TEXT only (contract §6).

    ``revtable.anchor = titleblock_left`` is the only anchor R1 draws: the
    table's top-right corner meets the title block's top-left corner and the
    table grows left and down, which is where a Korean construction drawing
    carries its revision history. Never a TABLE entity -- ZWCAD 2026 and the
    viewer both have to read this, and an ACAD_TABLE is a proxy in half the
    programs that will open the file (brief Constraints).

    The header row is ``revtable.columns`` itself; there is no separate header
    setting (contract §6). Values are placed by column position: 번호, 내용,
    일자, and any further column a project adds is drawn empty rather than
    guessed at.
    """
    if not rows:
        return None, []

    settings = config.revtable
    widths = [width * factor for width in settings.col_widths]
    row_height = settings.row_height * factor
    text_height = settings.text_height * factor
    #: Cell padding: half of what the row height has left over after the text.
    #: Derived rather than configured so a project that enlarges `text_height`
    #: does not have to remember a second number.
    pad = max((row_height - text_height) / 2.0, 0.0)

    box, warnings = titleblock_bbox(doc, frame)
    if box is None:
        # No measurable title block: anchor on the frame's bottom-right corner,
        # where `frames.yaml`'s fallback rule says the title block would be.
        right = frame.bbox[2] if len(frame.bbox) == 4 else 0.0
        top = frame.bbox[1] if len(frame.bbox) == 4 else 0.0
    else:
        right, top = box[0], box[3]

    total_width = sum(widths)
    left = right - total_width
    bottom = top - row_height * (len(rows) + 1)

    if len(frame.bbox) == 4 and not (
        frame.bbox[0] <= left
        and frame.bbox[1] <= bottom
        and right <= frame.bbox[2]
        and top <= frame.bbox[3]
    ):
        # Brief Defaults for ambiguity: a sheet whose title block sits too close
        # to the left edge, or one with many approved clusters, gets its table
        # drawn outside the 도곽 rather than squeezed, and the run says so.
        warnings.append(WARN_TABLE_OUTSIDE_FRAME)

    column_x = [left]
    for width in widths:
        column_x.append(column_x[-1] + width)
    row_y = [top - row_height * index for index in range(len(rows) + 2)]

    msp = doc.modelspace()
    attribs = {"layer": layer_name}
    for y in row_y:
        msp.add_line((_r(left), _r(y)), (_r(right), _r(y)), dxfattribs=dict(attribs))
    for x in column_x:
        msp.add_line((_r(x), _r(top)), (_r(x), _r(bottom)), dxfattribs=dict(attribs))

    cells = [list(settings.columns)]
    cells.extend([str(row.number), row.content, run_date] for row in rows)
    for row_index, values in enumerate(cells):
        center_y = row_y[row_index] - row_height / 2.0
        for column_index in range(len(widths)):
            value = values[column_index] if column_index < len(values) else ""
            if not value:
                continue
            _draw_cell(
                msp,
                value=value,
                x0=column_x[column_index],
                x1=column_x[column_index + 1],
                center_y=center_y,
                pad=pad,
                height=text_height,
                # The header and the narrow first/last columns read better
                # centred; 내용 is a sentence and is set from the left.
                centered=row_index == 0 or column_index == 0 or column_index == len(widths) - 1,
                attribs=attribs,
            )

    return (
        RevisionTable(
            left=_r(left),
            right=_r(right),
            top=_r(top),
            bottom=_r(bottom),
            column_x=[_r(value) for value in column_x],
            row_y=[_r(value) for value in row_y],
            rows=list(rows),
        ),
        warnings,
    )


def _draw_cell(
    msp: Any,
    *,
    value: str,
    x0: float,
    x1: float,
    center_y: float,
    pad: float,
    height: float,
    centered: bool,
    attribs: dict[str, Any],
) -> None:
    available = (x1 - x0) - pad * 2
    text = fit_text(value, height, available)
    if not text:
        return
    entity = msp.add_text(
        text,
        dxfattribs={**attribs, "height": _r(height), "style": "Standard"},
    )
    if centered:
        entity.set_placement(
            (_r((x0 + x1) / 2.0), _r(center_y)),
            align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER,
        )
    else:
        entity.set_placement(
            (_r(x0 + pad), _r(center_y)),
            align=ezdxf.enums.TextEntityAlignment.MIDDLE_LEFT,
        )


def _r(value: float) -> float:
    """Three decimals, and no ``-0.0`` (contract §8)."""
    rounded = round(float(value), 3)
    return 0.0 if rounded == 0.0 else rounded


# --------------------------------------------------------------------------- the drawing


def write_markup_dxf(
    *,
    after_working_dxf: Path,
    clusters: list[dict[str, Any]],
    frame: FrameRecord,
    run_date: str,
    layer_name: str,
    config: CompareConfig,
    out_path: Path,
    allowed_roots: list[Path] | None = None,
) -> MarkupResult | None:
    """Write one 도곽 짝's markup DXF, or ``None`` when nothing was approved.

    ``clusters`` are the sidecar's cluster objects with the review merged in
    (``clusters.json`` plus the ``cluster`` table's ``decision``/``user_label``);
    only the approved ones are drawn. ``frame`` is the 후 도곽 -- its scale sets
    every size and its title block positions the table.

    The 후 working DXF is *read*, never written: the file this produces is a new
    one under the bundle (CLAUDE.md rule 1, enforced by ``allowed_roots``).
    """
    drawn = approved_clusters(clusters)
    if not drawn:
        # Contract §6: a sheet with no approved cluster is not exported at all,
        # so there is nothing to write and no empty file to clean up later.
        return None

    doc = ezdxf.readfile(str(after_working_dxf))
    factor = scale_factor(frame.scale_denominator)
    warnings: list[str] = []

    _ensure_appid(doc)
    _ensure_layer(doc, layer_name, config.cloud.color)

    msp = doc.modelspace()
    for cluster in drawn:
        number = int(cluster["number"])
        _draw_cloud(msp, cluster, layer_name=layer_name, number=number)
        _draw_badge(
            msp, cluster, config=config, factor=factor, layer_name=layer_name, number=number
        )

    table, table_warnings = draw_revision_table(
        doc,
        frame=frame,
        rows=[
            RevisionRow(number=int(cluster["number"]), content=cluster_content(cluster))
            for cluster in drawn
        ],
        run_date=run_date,
        layer_name=layer_name,
        config=config,
        factor=factor,
    )
    warnings.extend(table_warnings)

    pin_header_for_determinism(doc, run_date)
    audit = doc.audit()
    if audit.errors:
        warnings.extend(f"audit:{error.code}" for error in audit.errors)
        logger.warning("markup DXF audit reported %d errors", len(audit.errors))

    payload = serialize(doc, run_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_path(out_path, allowed_roots=allowed_roots or [out_path.parent])
    out_path.write_bytes(payload)

    return MarkupResult(
        path=out_path,
        layer_name=layer_name,
        numbers=[int(cluster["number"]) for cluster in drawn],
        table=table,
        sha256=hashlib.sha256(payload).hexdigest(),
        warnings=warnings,
    )


def _draw_cloud(msp: Any, cluster: dict[str, Any], *, layer_name: str, number: int) -> None:
    """The cloud LWPOLYLINE, with the sidecar's own ``[x, y, bulge]`` vertices.

    Not recomputed from the box: what the reviewer approved on screen C is this
    polyline, and the printed drawing has to be the same one (contract §5).
    """
    points = [
        (float(point[0]), float(point[1]), 0.0, 0.0, float(point[2]))
        for point in cluster["cloud"]["points"]
    ]
    cloud = msp.add_lwpolyline(points, format="xyseb", close=True, dxfattribs={"layer": layer_name})
    _set_xdata(cloud, number, "cloud")


def _draw_badge(
    msp: Any,
    cluster: dict[str, Any],
    *,
    config: CompareConfig,
    factor: float,
    layer_name: str,
    number: int,
) -> None:
    """The numbered triangle: shape from :func:`badge_geometry`, position from the sidecar.

    The sidecar carries the badge's ``center`` but not its three corners
    (``clusters-sidecar.schema.json``), so the triangle is rebuilt with the
    function that produced it in the first place -- same box, same settings,
    same scale, therefore the same points as the compare DXF.
    """
    badge = badge_geometry([float(value) for value in cluster["bbox"]], config, factor)
    shape = msp.add_lwpolyline(
        [(x, y) for x, y in badge.points],
        format="xy",
        close=True,
        dxfattribs={"layer": layer_name},
    )
    _set_xdata(shape, number, "badge_shape")

    text = msp.add_text(
        str(number),
        dxfattribs={
            "layer": layer_name,
            "height": badge.text_height,
            "style": "Standard",
        },
    )
    center = cluster.get("badge", {}).get("center") or list(badge.center)
    text.set_placement(
        (float(center[0]), float(center[1])),
        align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER,
    )
    _set_xdata(text, number, "badge_text")


__all__ = [
    "DECISION_APPROVED",
    "ELLIPSIS",
    "MARKUP_DXF_NAME",
    "NARROW_CHAR_RATIO",
    "WARN_NO_TITLEBLOCK_BBOX",
    "WARN_TABLE_OUTSIDE_FRAME",
    "WIDE_CHAR_RATIO",
    "MarkupResult",
    "RevisionRow",
    "RevisionTable",
    "approved_clusters",
    "cluster_content",
    "draw_revision_table",
    "fit_text",
    "text_width",
    "titleblock_bbox",
    "write_markup_dxf",
]
