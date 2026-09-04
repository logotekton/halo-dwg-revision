"""클러스터: turning changes into numbered cloud marks (contract §5, brief R1-06 §2).

A revision drawing does not carry one cloud mark per entity. It carries one per
*place something happened*, numbered in reading order, and the number is what
the revision table's rows and the site conversation are about. So this module
answers three questions:

* **What belongs together?** Changes whose boxes come within the grouping
  distance -- ``max(frame long side x cluster.grow_ratio, cluster.grow_min x
  scale_factor)`` -- are one cluster. Grouping is a union-find over a spatial
  grid rather than an all-pairs test, because a sheet that was largely redrawn
  can produce thousands of changes.
* **What number does it get?** Reading order: rows from the top, left to right
  inside a row. Two people looking at the same drawing have to call the same
  cloud "3".
* **Where exactly is the cloud drawn?** :func:`cloud_polyline` and
  :func:`badge_geometry` are the single source of those coordinates. R1-06
  writes them into the compare DXF, R1-09 draws the same numbers on the markup
  DWG, and both read the same functions so the two drawings cannot drift.

Minor changes never reach here (contract §3): they are recorded, listed and
filtered on the review screen, but they do not get a cloud mark, a number or a
revision-table row.

Every length is a ``compare.yaml`` ``cloud`` value in millimetres at 1:100,
multiplied by ``scale_factor`` (``compare/config.py``) -- a 1:50 sheet draws a
50mm arc so the cloud looks the same size on paper
(``docs/contracts/compare-dxf.md`` §5).
"""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from halo_engine.compare.config import CompareConfig
from halo_engine.compare.diff import KIND_BLOCKDEF, ChangeRecord
from halo_engine.compare.frames import FrameRecord
from halo_engine.compare.labels import auto_label, dominant_kind
from halo_engine.compare.signatures import union_boxes

#: Decimal places for every coordinate written into the sidecar or the DXF
#: (``docs/contracts/compare-dxf.md`` §8).
COORD_DECIMALS = 3

#: How much of the frame's long side a ``blockdef`` change may span before it
#: is split into one cluster per instance (brief Defaults for ambiguity). Six
#: doors spread over a floor plan are six places a person has to look at, not
#: one cloud mark around the whole sheet.
BLOCKDEF_SPLIT_RATIO = 0.30

#: Characters of the SHA-256 kept as ``cluster.signature``. Sixteen hex
#: characters is 64 bits: enough that two different clusters on one sheet will
#: not collide, short enough to read in a log line.
SIGNATURE_LENGTH = 16

#: ``sqrt(3)/2`` -- the height of an equilateral triangle over its side.
_TRIANGLE_HEIGHT = math.sqrt(3.0) / 2.0


def _r(value: float) -> float:
    rounded = round(float(value), COORD_DECIMALS)
    return 0.0 if rounded == 0.0 else rounded


@dataclass
class BadgeGeometry:
    """The numbered triangle: three points, its centroid and the text height.

    Returned rather than drawn so that R1-09's markup writer can place exactly
    the same triangle on the DWG that the viewer sees on the compare DXF.
    """

    points: list[tuple[float, float]]
    """The equilateral triangle, counter-clockwise, base first, apex up."""

    center: tuple[float, float]
    """Centroid -- the TEXT insertion point and the sidecar's ``badge.center``."""

    text_height: float
    """``cloud.badge_text_height`` x ``scale_factor``."""

    side: float
    """``cloud.badge_side`` x ``scale_factor``; the triangle's edge length."""


@dataclass
class ClusterRecord:
    """One ``cluster`` row before it is written (contract §3, sidecar §7).

    Picklable: clustering happens in the worker process alongside the diff.
    """

    number: int
    """1-based cloud-mark number in reading order. ``id`` is ``c<number>``."""

    signature: str
    """Hash of the members' ``(kind, before_handle, after_handle)`` tuples."""

    bbox: list[float] = field(default_factory=list)
    """Union of the member boxes, *before* the cloud margin, in 후 world mm."""

    kind: str = "modified"
    """Dominant member ``change.kind``, or ``mixed``."""

    label: str = ""
    """Automatic Korean label (``compare/labels.py``)."""

    change_seqs: list[int] = field(default_factory=list)
    """Member ``change.seq`` values, ascending. The sidecar writes ``ch<seq>``."""

    cloud: dict[str, Any] = field(default_factory=dict)
    """``{handle, points}`` -- the cloud LWPOLYLINE (contract §5)."""

    badge: dict[str, Any] = field(default_factory=dict)
    """``{shape_handle, text_handle, center}`` -- the number triangle."""

    badge_points: list[tuple[float, float]] = field(default_factory=list)
    """The triangle itself. Not a column and not in the sidecar; the DXF writer
    draws it and R1-09 recomputes it with :func:`badge_geometry`."""

    badge_text_height: float = 0.0
    """Height of the number TEXT, already scaled."""

    @property
    def id(self) -> str:
        return f"c{self.number}"

    def to_row(self) -> dict[str, Any]:
        """The ``cluster`` columns ``repos.replace_clusters`` inserts."""
        return {
            "number": self.number,
            "signature": self.signature,
            "bbox": list(self.bbox),
            "kind": self.kind,
            "label": self.label,
            "change_seqs": list(self.change_seqs),
            "cloud": dict(self.cloud),
            "badge": dict(self.badge),
        }


def cluster_signature(changes: list[ChangeRecord]) -> str:
    """Stable identity of a cluster across re-comparisons (contract §7).

    The sorted ``(kind, before_handle, after_handle)`` tuples of its members,
    hashed. Deliberately *not* the number or the box: re-running the comparison
    renumbers clusters and nudges boxes, and the user's 승인 has to survive
    that. It is also deliberately not the change ids -- those are positions in
    a list that shifts whenever a change is added earlier on the sheet.
    """
    parts = sorted(
        (change.kind, change.before_handle or "", change.after_handle or "") for change in changes
    )
    payload = "\n".join("\t".join(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:SIGNATURE_LENGTH]


def grouping_distance(frame: FrameRecord, config: CompareConfig, scale_factor: float) -> float:
    """How close two changes have to be to share a cloud mark, in millimetres."""
    long_side = max(frame.width, frame.height, 0.0)
    return max(long_side * config.cluster.grow_ratio, config.cluster.grow_min * scale_factor)


def cloud_polyline(
    bbox: list[float], config: CompareConfig, scale_factor: float
) -> list[tuple[float, float, float]]:
    """The cloud LWPOLYLINE around ``bbox``: ``[(x, y, bulge), ...]`` (contract §5).

    Counter-clockwise from the lower-left corner of ``bbox`` plus
    ``cloud.margin``, each side divided into equal chords of at most
    ``cloud.arc`` (at least one per side), every vertex carrying
    ``cloud.arc_bulge``. Counter-clockwise plus a positive bulge is what makes
    the arcs bulge *outwards*: the arc of a positive bulge turns
    counter-clockwise from the vertex to the next one, so on a
    counter-clockwise rectangle its centre falls inside and the arc falls
    outside.
    """
    margin = config.cloud.margin * scale_factor
    arc = max(config.cloud.arc * scale_factor, 1e-6)
    bulge = config.cloud.arc_bulge
    x0, y0, x1, y1 = (bbox[0] - margin, bbox[1] - margin, bbox[2] + margin, bbox[3] + margin)

    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    points: list[tuple[float, float, float]] = []
    for index, (sx, sy) in enumerate(corners):
        ex, ey = corners[(index + 1) % 4]
        length = math.hypot(ex - sx, ey - sy)
        steps = max(1, math.ceil(length / arc))
        for step in range(steps):
            ratio = step / steps
            points.append((_r(sx + (ex - sx) * ratio), _r(sy + (ey - sy) * ratio), bulge))
    return points


def badge_geometry(
    bbox: list[float], config: CompareConfig, scale_factor: float
) -> BadgeGeometry:
    """The number triangle outside the cloud's top-right corner (contract §5).

    ``cloud.badge_anchor = top_right`` is the only anchor R1 draws: the
    triangle's base starts at the cloud rectangle's top-right corner and runs
    east, with the apex up, so the badge never covers the drawing it annotates.
    """
    margin = config.cloud.margin * scale_factor
    side = config.cloud.badge_side * scale_factor
    corner_x = bbox[2] + margin
    corner_y = bbox[3] + margin
    points = [
        (_r(corner_x), _r(corner_y)),
        (_r(corner_x + side), _r(corner_y)),
        (_r(corner_x + side / 2.0), _r(corner_y + side * _TRIANGLE_HEIGHT)),
    ]
    center = (_r(corner_x + side / 2.0), _r(corner_y + side * _TRIANGLE_HEIGHT / 3.0))
    return BadgeGeometry(
        points=points,
        center=center,
        text_height=_r(config.cloud.badge_text_height * scale_factor),
        side=_r(side),
    )


# --------------------------------------------------------------------------- grouping


@dataclass
class _Unit:
    """One box that wants a cloud mark, and the change it belongs to."""

    box: list[float]
    seq: int


def _units(
    changes: list[ChangeRecord], frame: FrameRecord
) -> list[_Unit]:
    """One unit per change -- or one per instance for a spread-out ``blockdef``.

    Brief Defaults for ambiguity: when the references of a changed block span
    more than :data:`BLOCKDEF_SPLIT_RATIO` of the frame's long side, one cloud
    around all of them would be a cloud around the whole sheet, which tells the
    reviewer nothing. Each instance gets its own mark instead, all pointing at
    the same change record.
    """
    long_side = max(frame.width, frame.height, 0.0)
    units: list[_Unit] = []
    for change in changes:
        if change.kind == KIND_BLOCKDEF and change.instance_boxes:
            span = max(
                change.bbox[2] - change.bbox[0], change.bbox[3] - change.bbox[1]
            )
            if long_side > 0 and span > long_side * BLOCKDEF_SPLIT_RATIO:
                units.extend(_Unit(box=list(box), seq=change.seq) for box in change.instance_boxes)
                continue
        units.append(_Unit(box=list(change.bbox), seq=change.seq))
    return units


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, item: int) -> int:
        while self._parent[item] != item:
            self._parent[item] = self._parent[self._parent[item]]
            item = self._parent[item]
        return item

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def _group(units: list[_Unit], distance: float) -> list[list[int]]:
    """Union-find over boxes grown by half the grouping distance.

    Growing each box by ``distance / 2`` and testing for overlap makes two
    changes group when the gap between them is at most ``distance``, which is
    what ``compare.yaml`` promises ("이 거리 안에 있는 변경들을 한 클러스터로
    묶는다"). The spatial grid keeps it linear: a sheet that was redrawn can
    hand this function tens of thousands of boxes.
    """
    if not units:
        return []
    pad = distance / 2.0
    cell = max(distance, 1.0)
    grown = [
        (unit.box[0] - pad, unit.box[1] - pad, unit.box[2] + pad, unit.box[3] + pad)
        for unit in units
    ]

    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (x0, y0, x1, y1) in enumerate(grown):
        for cx in range(math.floor(x0 / cell), math.floor(x1 / cell) + 1):
            for cy in range(math.floor(y0 / cell), math.floor(y1 / cell) + 1):
                buckets[(cx, cy)].append(index)

    union = _UnionFind(len(units))
    for key in sorted(buckets):
        members = buckets[key]
        for position, left in enumerate(members):
            for right in members[position + 1 :]:
                a, b = grown[left], grown[right]
                if not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]):
                    union.union(left, right)

    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(units)):
        groups[union.find(index)].append(index)
    return [groups[root] for root in sorted(groups)]


def _reading_order(boxes: list[list[float]]) -> list[int]:
    """Indices in the order a person reads the sheet: rows from the top, left first.

    Rows are found by vertical overlap with the topmost box that has not been
    placed yet, so two clouds side by side get consecutive numbers even when
    their tops are a few millimetres apart, while a cloud a metre lower starts
    a new row.
    """
    remaining = sorted(range(len(boxes)), key=lambda i: (-boxes[i][3], boxes[i][0], i))
    order: list[int] = []
    while remaining:
        seed = boxes[remaining[0]]
        row = [i for i in remaining if boxes[i][3] >= seed[1] and boxes[i][1] <= seed[3]]
        row.sort(key=lambda i: (boxes[i][0], -boxes[i][3], i))
        order.extend(row)
        placed = set(row)
        remaining = [i for i in remaining if i not in placed]
    return order


def build_clusters(
    changes: list[ChangeRecord],
    frame: FrameRecord,
    config: CompareConfig,
    scale_factor: float = 1.0,
) -> list[ClusterRecord]:
    """Group the pair's real changes into numbered cloud marks.

    ``changes`` may contain minor records -- they are filtered here, so callers
    never have to remember the rule. ``frame`` is the 후 도곽 (its long side
    sets the grouping distance and its corner is the coordinate origin every
    box already uses), and ``scale_factor`` comes from that frame's scale
    denominator (``compare/config.py::scale_factor``).
    """
    real = [change for change in changes if not change.minor]
    if not real:
        return []
    by_seq = {change.seq: change for change in real}

    units = _units(real, frame)
    groups = _group(units, grouping_distance(frame, config, scale_factor))
    boxes = [union_boxes([units[index].box for index in group]) for group in groups]

    clusters: list[ClusterRecord] = []
    for number, position in enumerate(_reading_order(boxes), start=1):
        group = groups[position]
        bbox = boxes[position]
        seqs = sorted({units[index].seq for index in group})
        members = [by_seq[seq] for seq in seqs]
        badge = badge_geometry(bbox, config, scale_factor)
        clusters.append(
            ClusterRecord(
                number=number,
                signature=cluster_signature(members),
                bbox=bbox,
                kind=dominant_kind(members),
                label=auto_label(members),
                change_seqs=seqs,
                cloud={
                    "handle": None,
                    "points": [list(point) for point in cloud_polyline(bbox, config, scale_factor)],
                },
                badge={
                    "shape_handle": None,
                    "text_handle": None,
                    "center": [badge.center[0], badge.center[1]],
                },
                badge_points=badge.points,
                badge_text_height=badge.text_height,
            )
        )
    return clusters


__all__ = [
    "BLOCKDEF_SPLIT_RATIO",
    "COORD_DECIMALS",
    "SIGNATURE_LENGTH",
    "BadgeGeometry",
    "ClusterRecord",
    "badge_geometry",
    "build_clusters",
    "cloud_polyline",
    "cluster_signature",
    "grouping_distance",
]
