"""Shared plumbing for scenario modules -- not itself a scenario."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from compare_fixtures_gen.base_plan import save
from compare_fixtures_gen.truth import write_truth


def write_pair(
    out_root: Path,
    scenario_id: str,
    before_doc,
    after_doc,
    truth_data: dict[str, Any],
    *,
    before_name: str = "A-101.dxf",
    after_name: str = "A-101.dxf",
) -> None:
    base = out_root / scenario_id
    save(before_doc, base / "before" / before_name)
    save(after_doc, base / "after" / after_name)
    write_truth(base / "truth.json", truth_data)
