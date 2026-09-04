"""Build and write ``truth.json`` matching ``packages/schema/src/compare/truth.schema.json``
(`RevisionTruth`, docs/contracts/r1.md SS4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "0.1"


def expected_change(
    *,
    kind: str,
    etype: str,
    minor: bool,
    layer: str | None = None,
    before_handle: str | None = None,
    after_handle: str | None = None,
    minor_reason: str | None = None,
    bbox: list[float] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "kind": kind,
        "etype": etype,
        "minor": minor,
        "before_handle": before_handle,
        "after_handle": after_handle,
        "minor_reason": minor_reason,
    }
    if layer is not None:
        d["layer"] = layer
    if bbox is not None:
        d["bbox"] = bbox
    if note is not None:
        d["note"] = note
    return d


def expected_pair(
    *,
    sheet_no: str | None,
    status: str,
    match_method: str | None = None,
    expected_changes: list[dict[str, Any]] | None = None,
    expected_cluster_count: int | None = None,
    clean_regions: list[list[float]] | None = None,
) -> dict[str, Any]:
    return {
        "sheet_no": sheet_no,
        "status": status,
        "match_method": match_method,
        "expected_changes": expected_changes or [],
        "expected_cluster_count": expected_cluster_count,
        "clean_regions": clean_regions or [],
    }


def build_truth(
    *,
    scenario: str,
    description: str,
    expected_pairs: list[dict[str, Any]],
    before_dir: str = "before",
    after_dir: str = "after",
    notes: str | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "scenario": scenario,
        "description": description,
        "before_dir": before_dir,
        "after_dir": after_dir,
        "expected_pairs": expected_pairs,
    }
    if notes is not None:
        d["notes"] = notes
    return d


def write_truth(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.write_text(text, encoding="utf-8")
