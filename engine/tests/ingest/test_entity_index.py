from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from halo_engine.ingest.entity_index import iter_entity_records, write_jsonl


def test_iter_entity_records_top_level_only_plus_attribs(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F02.dxf"))
    records = list(iter_entity_records(doc))

    inserts = [r for r in records if r.etype == "INSERT"]
    attribs = [r for r in records if r.etype == "ATTRIB"]
    assert len(inserts) == 30
    assert len(attribs) == 60  # TAG + SIZE per insert
    assert all(r.block_name for r in inserts)
    assert all(r.block_name is None for r in attribs)
    assert all(r.text is not None for r in attribs)


def test_iter_entity_records_handles_and_bboxes_are_populated(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F06.dxf"))
    records = list(iter_entity_records(doc))
    assert records
    for r in records:
        assert r.handle
        assert r.space == "MODEL"
    lines = [r for r in records if r.etype == "LINE"]
    assert all(r.length is not None and r.length > 0 for r in lines)
    hatches = [r for r in records if r.etype == "HATCH"]
    assert all(r.area is not None and r.area > 0 for r in hatches)
    assert all(r.bbox is not None and len(r.bbox) == 4 for r in lines)


def test_write_jsonl_round_trips(generated_dir: Path, tmp_path: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F01.dxf"))
    records = list(iter_entity_records(doc))
    out = tmp_path / "entities.jsonl"

    count = write_jsonl(records, out)

    assert count == len(records)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(records)
    first = json.loads(lines[0])
    assert set(first.keys()) == {
        "handle",
        "etype",
        "layer",
        "space",
        "bbox",
        "length",
        "area",
        "text",
        "block_name",
    }
