"""Hand-built ``LayerStatsDocument``s for the crosscheck tests.

Kept out of ``conftest.py`` so the test modules can import it directly by
name; ``conftest.py`` only holds real pytest fixtures.
"""

from __future__ import annotations

import copy
from typing import Any


def empty_aggregate() -> dict[str, Any]:
    """Every measure at its zero value (``text_hash`` = sha1 of the empty string)."""
    return {
        "entity_count": 0,
        "count_by_type": {},
        "length_sum_mm": 0.0,
        "hatch_area_sum_mm2": 0.0,
        "text_count": 0,
        "text_hash": "da39a3ee5e6b4b0d",
        "insert_by_block": {},
    }


def stats_document(
    *,
    producer: str,
    buckets: list[tuple[str, str, dict[str, Any]]],
    file_sha256: str = "a" * 64,
) -> dict[str, Any]:
    """Minimal ``LayerStatsDocument``.

    ``buckets`` entries are ``(space, layer, partial aggregate)``; unmentioned
    measures are filled with their zero value so each test spells out only the
    measure it is about. ``totals`` is summed from the buckets.
    """
    full_buckets = []
    totals = empty_aggregate()
    for space, layer, partial in buckets:
        aggregate = empty_aggregate()
        aggregate.update(copy.deepcopy(partial))
        aggregate["entity_count"] = sum(aggregate["count_by_type"].values())
        full_buckets.append({"layer": layer, "space": space, "aggregate": aggregate})
        for name, count in aggregate["count_by_type"].items():
            totals["count_by_type"][name] = totals["count_by_type"].get(name, 0) + count
        for name, count in aggregate["insert_by_block"].items():
            totals["insert_by_block"][name] = totals["insert_by_block"].get(name, 0) + count
        totals["length_sum_mm"] += aggregate["length_sum_mm"]
        totals["hatch_area_sum_mm2"] += aggregate["hatch_area_sum_mm2"]
        totals["text_count"] += aggregate["text_count"]
    totals["entity_count"] = sum(totals["count_by_type"].values())
    return {
        "schema_version": "0.1",
        "file_sha256": file_sha256,
        "producer": {"name": producer, "version": "test"},
        "buckets": full_buckets,
        "totals": totals,
    }
