from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

import ezdxf

from halo_engine.ingest.stats import compute_layer_stats, entity_length, hatch_area


def _stats_for(path: Path) -> dict:
    doc = ezdxf.readfile(str(path))
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return compute_layer_stats(doc, file_sha256=sha256)


def test_f06_count_by_type_matches_brief_acceptance_check(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F06.dxf")
    assert stats["totals"]["count_by_type"] == {
        "HATCH": 12,
        "INSERT": 8,
        "LINE": 24,
        "LWPOLYLINE": 12,
        "TEXT": 30,
    }


def test_attrib_excluded_from_count_by_type_but_included_in_text_count(generated_dir: Path) -> None:
    """F02: 30 INSERTs each carrying TAG + SIZE ATTRIBs (docs/contracts/stats-definition.md)."""
    stats = _stats_for(generated_dir / "F02.dxf")
    assert "ATTRIB" not in stats["totals"]["count_by_type"]
    assert stats["totals"]["count_by_type"]["INSERT"] == 30
    # 30 inserts x 2 attribs each = 60 ATTRIB text values, all on A-TEXT.
    attext_bucket = next(
        b for b in stats["buckets"] if b["layer"] == "A-TEXT" and b["space"] == "MODEL"
    )
    assert attext_bucket["aggregate"]["text_count"] == 60
    assert "ATTRIB" not in attext_bucket["aggregate"]["count_by_type"]


def test_entity_count_is_sum_of_count_by_type(generated_dir: Path) -> None:
    for name in ("F01.dxf", "F02.dxf", "F06.dxf", "F09.dxf"):
        stats = _stats_for(generated_dir / name)
        for bucket in stats["buckets"]:
            agg = bucket["aggregate"]
            assert agg["entity_count"] == sum(agg["count_by_type"].values()), name
        totals = stats["totals"]
        assert totals["entity_count"] == sum(totals["count_by_type"].values())


def test_totals_equal_sum_over_buckets(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F06.dxf")
    by_type: dict[str, int] = {}
    text_count = 0
    length_sum = 0.0
    for bucket in stats["buckets"]:
        agg = bucket["aggregate"]
        for t, c in agg["count_by_type"].items():
            by_type[t] = by_type.get(t, 0) + c
        text_count += agg["text_count"]
        length_sum += agg["length_sum_mm"]
    assert by_type == stats["totals"]["count_by_type"]
    assert text_count == stats["totals"]["text_count"]
    assert round(length_sum, 6) == stats["totals"]["length_sum_mm"]


def test_bbox_is_min_max_object_form(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F06.dxf")
    bbox = stats["totals"]["bbox"]
    assert set(bbox.keys()) == {"min", "max"}
    assert len(bbox["min"]) == 2
    assert len(bbox["max"]) == 2
    assert bbox["min"][0] < bbox["max"][0]
    assert bbox["min"][1] < bbox["max"][1]


def test_text_hash_empty_set_is_hash_of_empty_string(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F01.dxf")
    empty_hash = hashlib.sha1(b"").hexdigest()[:16]
    for bucket in stats["buckets"]:
        agg = bucket["aggregate"]
        if agg["text_count"] == 0:
            assert agg["text_hash"] == empty_hash


def test_text_hash_is_nfc_codepoint_sorted_join_sha1_16(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F03.dxf")
    doc = ezdxf.readfile(str(generated_dir / "F03.dxf"))
    texts = [unicodedata.normalize("NFC", e.dxf.text) for e in doc.modelspace().query("TEXT")]
    texts += [unicodedata.normalize("NFC", e.text) for e in doc.modelspace().query("MTEXT")]
    joined = "\n".join(sorted(texts))
    expected = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]
    assert stats["totals"]["text_hash"] == expected


def test_ellipse_contributes_to_length_sum(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F01.dxf"))
    ellipses = list(doc.modelspace().query("ELLIPSE"))
    assert ellipses, "F01 is expected to contain ELLIPSE entities"
    total = sum(entity_length(e) for e in ellipses)
    assert total > 0


def test_hatch_area_matches_known_f06_column_fill(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F06.dxf"))
    hatches = list(doc.modelspace().query("HATCH"))
    assert len(hatches) == 12
    # every F06 column hatch is a solid 600x600 fill.
    for h in hatches:
        assert abs(hatch_area(h) - 600.0 * 600.0) < 1e-6


def test_bucket_ordering_is_layer_then_space(generated_dir: Path) -> None:
    stats = _stats_for(generated_dir / "F06.dxf")
    keys = [(b["layer"], b["space"]) for b in stats["buckets"]]
    assert keys == sorted(keys)


def test_paper_space_label_uses_layout_name(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4
    layout = doc.layout("Layout1")
    layout.add_line((0, 0), (10, 10), dxfattribs={"layer": "0"})
    p = tmp_path / "paper.dxf"
    doc.saveas(str(p))

    stats = _stats_for(p)
    spaces = {b["space"] for b in stats["buckets"]}
    assert "PAPER:Layout1" in spaces
