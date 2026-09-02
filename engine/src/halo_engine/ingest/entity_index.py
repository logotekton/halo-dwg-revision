"""Flat per-top-level-entity record generator (brief W2-03).

One record per top-level entity of every space (never per block-definition
content -- same "top-level only" rule as :mod:`halo_engine.ingest.stats`),
plus one record per ATTRIB owned by a top-level INSERT. SQLite storage is
W6-01; this module only produces the records, as an iterable or JSONL.
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Layout

from halo_engine.ingest.stats import LENGTH_TYPES, entity_length, hatch_area


@dataclass(frozen=True)
class EntityRecord:
    handle: str
    etype: str
    layer: str
    space: str
    bbox: list[float] | None
    length: float | None
    area: float | None
    text: str | None
    block_name: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _space_label(layout: Layout) -> str:
    return "MODEL" if layout.name == "Model" else f"PAPER:{layout.name}"


def _bbox_of_one(entity: DXFGraphic) -> list[float] | None:
    box = ezdxf.bbox.extents([entity])
    if not box.has_data:
        return None
    return [
        round(float(box.extmin.x), 6),
        round(float(box.extmin.y), 6),
        round(float(box.extmax.x), 6),
        round(float(box.extmax.y), 6),
    ]


def _record_for(entity: DXFGraphic, space: str) -> EntityRecord:
    etype = entity.dxftype()
    length = entity_length(entity) if etype in LENGTH_TYPES else None
    area = hatch_area(entity) if etype == "HATCH" else None
    text: str | None = None
    if etype == "TEXT":
        text = entity.dxf.text
    elif etype == "MTEXT":
        text = entity.text
    elif etype == "ATTRIB":
        text = entity.dxf.text
    block_name = unicodedata.normalize("NFC", entity.dxf.name) if etype == "INSERT" else None
    return EntityRecord(
        handle=entity.dxf.handle,
        etype=etype,
        layer=unicodedata.normalize("NFC", entity.dxf.layer),
        space=space,
        bbox=_bbox_of_one(entity),
        length=length,
        area=area,
        text=text,
        block_name=block_name,
    )


def iter_entity_records(doc: Drawing) -> Iterator[EntityRecord]:
    """Yield one :class:`EntityRecord` per top-level entity (plus ATTRIBs)."""
    spaces = [doc.modelspace()]
    for layout in doc.layouts:
        if layout.name == "Model":
            continue
        if len(layout) == 0:
            continue
        spaces.append(layout)

    for layout in spaces:
        space = _space_label(layout)
        for entity in layout:
            yield _record_for(entity, space)
            if entity.dxftype() == "INSERT":
                for attrib in entity.attribs:
                    yield _record_for(attrib, space)


def write_jsonl(records: Iterator[EntityRecord] | list[EntityRecord], path: str | Path) -> int:
    """Write ``records`` as JSONL (one compact JSON object per line). Returns the count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record.to_dict(), ensure_ascii=False))
            fh.write("\n")
            count += 1
    return count


__all__ = ["EntityRecord", "iter_entity_records", "write_jsonl"]
