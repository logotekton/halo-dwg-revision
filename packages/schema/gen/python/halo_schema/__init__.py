"""Halo CAD contract schemas for Python.

The JSON Schema sources in ``packages/schema/src`` are the single source of
truth. Two things are generated from them and committed:

``halo_schema.models``
    pydantic v2 models, written by ``scripts/gen-python.sh``. They describe the
    *shape* of every document.
``halo_schema.schemas``
    a verbatim copy of the schema sources, shipped as package data so
    :mod:`halo_schema.validation` can enforce the conditional rules that
    pydantic cannot express, above all the ADR-0003 height comparison rules.

This module and :mod:`halo_schema.validation` are hand written; everything
under ``models/`` and ``schemas/`` is regenerated and must not be edited.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_BASE_URI = "https://schema.halo-cad.internal/v0/"
"""Base URI of every schema ``$id``. ``.internal`` is reserved for private use,
so the URI is stable and is never fetched: schemas are read from this package."""

SCHEMA_VERSION = "0.1"
"""Current contract version, written into the ``schema_version`` field."""

BRIDGE_PROTOCOL_VERSION = "0.1"
"""Version of the 3D iframe postMessage protocol (ADR-0004)."""

SCHEMA_FILES: dict[str, str] = {
    "primitives": "common/primitives.schema.json",
    "provenance": "common/provenance.schema.json",
    "entity_ref": "common/entity-ref.schema.json",
    "ndj_document": "ndj/document.schema.json",
    "ndj_entity": "ndj/entity.schema.json",
    "layer_stats": "stats/layer-stats.schema.json",
    "level_observation": "levels/level-observation.schema.json",
    "floor_levels": "levels/floor-levels.schema.json",
    "consistency_check_set": "levels/consistency-check.schema.json",
    "markup_sidecar": "sidecar/markup.schema.json",
    "tags_sidecar": "sidecar/tags.schema.json",
    "bridge_message": "bridge/messages.schema.json",
    # R1 revision comparison (docs/contracts/r1.md §4). Same order and the same
    # eight files as `SCHEMA_IDS` in packages/schema/src/schemas.ts; the keys
    # differ only in spelling (snake_case, `compare_` prefixed) so a Python
    # caller reads `assert_valid("compare_clusters_sidecar", ...)`.
    "compare_sheet_frame": "compare/sheet-frame.schema.json",
    "compare_sheet_pair": "compare/sheet-pair.schema.json",
    "compare_change": "compare/change.schema.json",
    "compare_cluster": "compare/cluster.schema.json",
    "compare_run": "compare/run.schema.json",
    "compare_clusters_sidecar": "compare/clusters-sidecar.schema.json",
    "compare_set_summary": "compare/compare-set.schema.json",
    "compare_truth": "compare/truth.schema.json",
}

SCHEMA_IDS: dict[str, str] = {
    key: SCHEMA_BASE_URI + rel for key, rel in SCHEMA_FILES.items()
}

CONSISTENCY_CHECK_POINTER = SCHEMA_IDS["consistency_check_set"] + "#/$defs/check"
"""Pointer to a single check definition inside the consistency check set."""

SCHEMAS_DIR = Path(__file__).parent / "schemas"


def schema_path(key: str) -> Path:
    """Filesystem path of one schema source shipped with the package."""
    try:
        relative = SCHEMA_FILES[key]
    except KeyError:  # pragma: no cover - programming error
        raise KeyError(f"unknown schema key {key!r}; known: {sorted(SCHEMA_FILES)}") from None
    return SCHEMAS_DIR / relative


@lru_cache(maxsize=None)
def load_schema(key: str) -> dict[str, Any]:
    """Parsed schema source, cached."""
    return json.loads(schema_path(key).read_text(encoding="utf-8"))


def all_schemas() -> dict[str, dict[str, Any]]:
    """Every schema source, keyed the same way as :data:`SCHEMA_IDS`."""
    return {key: load_schema(key) for key in SCHEMA_FILES}


__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "CONSISTENCY_CHECK_POINTER",
    "SCHEMAS_DIR",
    "SCHEMA_BASE_URI",
    "SCHEMA_FILES",
    "SCHEMA_IDS",
    "SCHEMA_VERSION",
    "all_schemas",
    "load_schema",
    "schema_path",
]
