"""``compare/labels.py``: the sentence that ends up in the revision table's 내용 column.

These strings are printed on a drawing that goes to site, so they are asserted
literally. A label that reads `INSERT moved dx=1250` would be a bug even though
nothing would crash.
"""

from __future__ import annotations

import pytest

from halo_engine.compare.diff import (
    KIND_ADDED,
    KIND_BLOCKDEF,
    KIND_DIMENSION,
    KIND_MODIFIED,
    KIND_MOVED,
    KIND_REMOVED,
    KIND_TEXT,
    ChangeRecord,
)
from halo_engine.compare.labels import auto_label, direction_of, dominant_kind, entity_name


def change(kind: str, etype: str, **kwargs: object) -> ChangeRecord:
    return ChangeRecord(
        seq=int(kwargs.pop("seq", 1)),
        kind=kind,
        etype=etype,
        layer=str(kwargs.pop("layer", "A-WALL")),
        bbox=[0.0, 0.0, 1.0, 1.0],
        delta=kwargs.pop("delta", None),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("etype", "block", "expected"),
    [
        ("LINE", None, "선"),
        ("LWPOLYLINE", None, "폴리라인"),
        ("POLYLINE", None, "폴리라인"),
        ("CIRCLE", None, "원"),
        ("ARC", None, "호"),
        ("TEXT", None, "문자"),
        ("MTEXT", None, "문자"),
        ("DIMENSION", None, "치수"),
        ("HATCH", None, "해치"),
        ("INSERT", "DOOR_900", "블록 DOOR_900"),
        ("INSERT", None, "블록"),
        ("WIPEOUT", None, "WIPEOUT"),
    ],
)
def test_entity_names_are_korean(etype: str, block: str | None, expected: str) -> None:
    assert entity_name(etype, block) == expected


@pytest.mark.parametrize(
    ("dx", "dy", "expected"),
    [
        (1000, 0, "동"),
        (1000, 1000, "북동"),
        (0, 1000, "북"),
        (-1000, 1000, "북서"),
        (-1000, 0, "서"),
        (-1000, -1000, "남서"),
        (0, -1000, "남"),
        (1000, -1000, "남동"),
        (0, 0, "동"),
    ],
)
def test_eight_compass_points(dx: float, dy: float, expected: str) -> None:
    assert direction_of(dx, dy) == expected


def test_a_move_says_how_far_and_which_way() -> None:
    label = auto_label(
        [
            change(
                KIND_MOVED,
                "INSERT",
                delta={"move": [1250.0, 0.0], "distance": 1250.0, "block": "DOOR_900"},
            )
        ]
    )
    assert label == "블록 DOOR_900 이동 1,250mm 동"


def test_added_and_removed() -> None:
    assert auto_label([change(KIND_ADDED, "LWPOLYLINE")]) == "폴리라인 신설"
    assert auto_label([change(KIND_REMOVED, "HATCH")]) == "해치 삭제"


def test_a_dimension_label_does_not_say_the_word_twice() -> None:
    label = auto_label(
        [change(KIND_DIMENSION, "DIMENSION", delta={"before": 12000.0, "after": 12500.0})]
    )
    assert label == "치수 12,000→12,500"


def test_a_text_change_quotes_both_strings() -> None:
    label = auto_label([change(KIND_TEXT, "TEXT", delta={"before": "거실", "after": "리빙룸"})])
    assert label == "문자 문구 거실→리빙룸"


def test_a_blockdef_change_counts_the_instances() -> None:
    label = auto_label(
        [change(KIND_BLOCKDEF, "INSERT", delta={"block": "DOOR_900", "instances": 6})]
    )
    assert label == "블록 DOOR_900 정의 변경 6곳"


def test_a_blockdef_change_without_a_name_reads_as_the_brief_writes_it() -> None:
    label = auto_label([change(KIND_BLOCKDEF, "INSERT", delta={"instances": 6})])
    assert label == "블록 정의 변경 6곳"


def test_a_mixed_cluster_names_the_commonest_type_and_counts_the_rest() -> None:
    label = auto_label(
        [
            change(KIND_REMOVED, "LWPOLYLINE", seq=1),
            change(KIND_REMOVED, "LWPOLYLINE", seq=2),
            change(KIND_REMOVED, "HATCH", seq=3),
        ]
    )
    assert label == "폴리라인 외 1건 삭제"


def test_a_plain_modification() -> None:
    assert auto_label([change(KIND_MODIFIED, "LINE")]) == "선 수정"


def test_no_changes_no_label() -> None:
    assert auto_label([]) == ""


def test_dominant_kind() -> None:
    assert dominant_kind([change(KIND_ADDED, "LINE")]) == KIND_ADDED
    assert (
        dominant_kind([change(KIND_ADDED, "LINE", seq=1), change(KIND_MOVED, "LINE", seq=2)])
        == "mixed"
    )
    assert dominant_kind([]) == KIND_MODIFIED
