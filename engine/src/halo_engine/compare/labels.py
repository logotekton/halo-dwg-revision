"""자동 문구: the Korean sentence printed inside a cloud mark's row (contract §6).

One cluster becomes one row of the revision table, and the 내용 column has to
read like something a person wrote: `블록 DOOR_900 이동 1,250mm 동`, not
`INSERT moved dx=1250`. The template is fixed by the contract --
``{종류} {행위}[ {수치}]`` -- and every word of it is Korean, because it is
printed on a drawing that goes to site (CLAUDE.md rule 8).

There is no dictionary of drawing terms in R1 (that is a week-2 feature), so
the 종류 is the entity type's Korean name and nothing more: a wall polyline is
`폴리라인`, not `벽`. Saying `폴리라인` is honest; guessing `벽` from a layer
name would be wrong on the first drawing that names its layers differently, and
the user can type over the label anyway (``cluster.user_label``).
"""

from __future__ import annotations

import math

from halo_engine.compare.diff import (
    KIND_ADDED,
    KIND_BLOCKDEF,
    KIND_DIMENSION,
    KIND_MOVED,
    KIND_REMOVED,
    KIND_TEXT,
    ChangeRecord,
)

#: Entity type -> what a Korean drawing calls it. Types outside the table keep
#: their DXF name, which is better than a wrong translation.
ENTITY_NAMES: dict[str, str] = {
    "LINE": "선",
    "LWPOLYLINE": "폴리라인",
    "POLYLINE": "폴리라인",
    "CIRCLE": "원",
    "ARC": "호",
    "ELLIPSE": "타원",
    "SPLINE": "스플라인",
    "TEXT": "문자",
    "MTEXT": "문자",
    "ATTRIB": "속성",
    "ATTDEF": "속성",
    "DIMENSION": "치수",
    "HATCH": "해치",
    "LEADER": "지시선",
    "MULTILEADER": "지시선",
    "POINT": "점",
    "SOLID": "솔리드",
    "TRACE": "솔리드",
    "3DFACE": "3D면",
    "INSERT": "블록",
    "VIEWPORT": "뷰포트",
}

#: The eight compass points, counter-clockwise from due east, as a site
#: engineer says them. A cloud mark that says `이동 1,250mm 동` can be checked
#: against the drawing without opening the file.
DIRECTIONS = ("동", "북동", "북", "북서", "서", "남서", "남", "남동")


def entity_name(etype: str, block_name: str | None = None) -> str:
    """`선`, `해치`, `블록 DOOR_900` -- the 종류 half of the label."""
    base = ENTITY_NAMES.get(etype, etype)
    if etype == "INSERT" and block_name:
        return f"{base} {block_name}"
    return base


def direction_of(dx: float, dy: float) -> str:
    """Which of :data:`DIRECTIONS` a translation points to. `동` when it is nowhere."""
    if dx == 0.0 and dy == 0.0:
        return DIRECTIONS[0]
    sector = int(round(math.degrees(math.atan2(dy, dx)) / 45.0)) % 8
    return DIRECTIONS[sector]


def _number(value: float) -> str:
    return f"{value:,.0f}"


def _text_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return _number(value)
    return str(value)


def _kind_counts(changes: list[ChangeRecord]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for change in changes:
        counts[change.kind] = counts.get(change.kind, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _type_label(changes: list[ChangeRecord]) -> str:
    """The dominant 종류, plus `외 n건` when the cluster mixes several."""
    names: dict[str, int] = {}
    for change in changes:
        block = None
        if change.kind == KIND_BLOCKDEF and change.delta:
            block = str(change.delta.get("block") or "") or None
        elif change.etype == "INSERT" and change.delta:
            block = str(change.delta.get("block") or "") or None
        name = entity_name(change.etype, block)
        names[name] = names.get(name, 0) + 1
    dominant, count = sorted(names.items(), key=lambda item: (-item[1], item[0]))[0]
    others = len(changes) - count
    return f"{dominant} 외 {others}건" if others else dominant


def _action(changes: list[ChangeRecord], kind: str) -> str:
    """The 행위 half: what was done, with the number that makes it checkable."""
    if kind == KIND_ADDED:
        return "신설"
    if kind == KIND_REMOVED:
        return "삭제"
    if kind == KIND_MOVED:
        moved = [c for c in changes if c.kind == KIND_MOVED and c.delta]
        if moved:
            delta = moved[0].delta or {}
            move = delta.get("move") or [0.0, 0.0]
            distance = float(delta.get("distance") or 0.0)
            return f"이동 {_number(distance)}mm {direction_of(float(move[0]), float(move[1]))}"
        return "이동"
    if kind == KIND_DIMENSION:
        first = next((c for c in changes if c.kind == KIND_DIMENSION and c.delta), None)
        if first is not None and first.delta is not None:
            before = _text_value(first.delta.get("before"))
            after = _text_value(first.delta.get("after"))
            if before or after:
                return f"치수 {before}→{after}"
        return "치수 변경"
    if kind == KIND_TEXT:
        first = next((c for c in changes if c.kind == KIND_TEXT and c.delta), None)
        if first is not None and first.delta is not None:
            before = _text_value(first.delta.get("before"))
            after = _text_value(first.delta.get("after"))
            if before or after:
                return f"문구 {before}→{after}"
        return "문구 변경"
    if kind == KIND_BLOCKDEF:
        # The 종류 half already says `블록 DOOR_900`, so the action says
        # `정의 변경 6곳` and the whole label reads `블록 DOOR_900 정의 변경 6곳`.
        # Without a block name the 종류 is just `블록` and the label comes out
        # as the brief's `블록 정의 변경 6곳`.
        instances = 0
        for change in changes:
            if change.kind == KIND_BLOCKDEF and change.delta:
                instances = max(instances, int(change.delta.get("instances") or 0))
        return f"정의 변경 {instances}곳" if instances else "정의 변경"
    return "수정"


def dominant_kind(changes: list[ChangeRecord]) -> str:
    """``cluster.kind``: the members' one kind, or ``mixed`` (contract §3)."""
    counts = _kind_counts(changes)
    if not counts:
        return "modified"
    if len(counts) == 1:
        return counts[0][0]
    return "mixed"


def auto_label(changes: list[ChangeRecord]) -> str:
    """``{종류} {행위}[ {수치}]`` for one cluster's changes (contract §6, brief §3).

    When the 종류 and the 행위 would repeat the same word -- a DIMENSION whose
    measurement changed is `치수` twice -- the label says it once. `치수 치수
    12,000→12,500` is not something anybody would write on a drawing.
    """
    if not changes:
        return ""
    kind = dominant_kind(changes)
    if kind == "mixed":
        counts = _kind_counts(changes)
        kind = counts[0][0]
    subject = _type_label(changes)
    action = _action(changes, kind)
    head = subject.split(" ")[0]
    if action.startswith(head + " "):
        return action
    return f"{subject} {action}"


__all__ = [
    "DIRECTIONS",
    "ENTITY_NAMES",
    "auto_label",
    "direction_of",
    "dominant_kind",
    "entity_name",
]
