"""Generation pipeline: build one fixture's DXF variant(s), then independently
re-read the written bytes with ezdxf to compute truth statistics.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import ezdxf

from fixtures_gen.base import BuildResult
from fixtures_gen.common import make_rng, save
from fixtures_gen.fixtures import (
    f01_basic,
    f02_blocks,
    f03_text,
    f04_hatch,
    f05_dimensions,
    f06_structural_plan,
    f07_schedule,
    f08_levels,
    f09_rooms,
    f10_xref,
    f11_large,
)
from fixtures_gen.stats import compute_stats

#: fixture id -> module with a ``build(version, rng) -> BuildResult`` function.
#: F10 (multi-file XREF pair) and F11/F12 (large tiled) are handled specially
#: below because their signature/output shape differs.
SIMPLE_FIXTURES: dict[str, Any] = {
    "F01": f01_basic,
    "F02": f02_blocks,
    "F03": f03_text,
    "F04": f04_hatch,
    "F05": f05_dimensions,
    "F06": f06_structural_plan,
    "F07": f07_schedule,
    "F08": f08_levels,
    "F09": f09_rooms,
}

ALL_FIXTURE_IDS = [*SIMPLE_FIXTURES.keys(), "F10", "F11", "F12"]

F11_TARGET_ENTITIES = 200_000
F12_TARGET_ENTITIES = 1_000_000


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8")


def _save_and_describe(doc, path: Path) -> dict:
    save(doc, path)
    stats_doc = ezdxf.readfile(str(path))
    return {
        "file": path.name,
        "dxf_version": stats_doc.dxfversion,
        "encoding": stats_doc.encoding,
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "stats": compute_stats(stats_doc),
    }


def generate_simple(fixture_id: str, out_dir: Path, truth_dir: Path) -> Path:
    module = SIMPLE_FIXTURES[fixture_id]

    rng_2018 = make_rng(fixture_id, "r2018")
    result_2018: BuildResult = module.build("R2018", rng_2018)
    primary_path = out_dir / f"{fixture_id}.dxf"
    primary_desc = _save_and_describe(result_2018.doc, primary_path)

    rng_2000 = make_rng(fixture_id, "r2000_cp949")
    result_2000: BuildResult = module.build("R2000", rng_2000)
    result_2000.doc.encoding = "cp949"
    variant_path = out_dir / f"{fixture_id}_r2000_cp949.dxf"
    variant_desc = _save_and_describe(result_2000.doc, variant_path)

    truth = {
        "fixture": fixture_id,
        "primary": primary_desc,
        "variants": {"r2000_cp949": {**variant_desc, "omitted": result_2000.omitted}},
        "totals": primary_desc["stats"]["totals"],
        "extra": result_2018.extra,
    }
    truth_path = truth_dir / f"{fixture_id}.json"
    _write_json(truth_path, truth)
    return truth_path


def generate_f10(out_dir: Path, truth_dir: Path) -> Path:
    rng_2018 = make_rng("F10", "r2018")
    pair_2018 = f10_xref.build_pair("R2018", rng_2018)
    grid_path = out_dir / "F10_grid.dxf"
    host_path = out_dir / "F10_host.dxf"
    # grid must be written first: the host's XREF path is resolved relative
    # to the host file's directory, both live side by side in `out_dir`.
    grid_desc = _save_and_describe(pair_2018["grid"].doc, grid_path)
    host_desc = _save_and_describe(pair_2018["host"].doc, host_path)

    rng_2000 = make_rng("F10", "r2000_cp949")
    pair_2000 = f10_xref.build_pair("R2000", rng_2000)
    pair_2000["grid"].doc.encoding = "cp949"
    pair_2000["host"].doc.encoding = "cp949"
    grid_r2000_path = out_dir / "F10_grid_r2000_cp949.dxf"
    host_r2000_path = out_dir / "F10_host_r2000_cp949.dxf"
    grid_r2000_desc = _save_and_describe(pair_2000["grid"].doc, grid_r2000_path)
    host_r2000_desc = _save_and_describe(pair_2000["host"].doc, host_r2000_path)

    truth = {
        "fixture": "F10",
        "primary": {"grid": grid_desc, "host": host_desc},
        "variants": {"r2000_cp949": {"grid": grid_r2000_desc, "host": host_r2000_desc}},
        "totals": {
            "grid": grid_desc["stats"]["totals"],
            "host": host_desc["stats"]["totals"],
        },
        "extra": {"grid": pair_2018["grid"].extra, "host": pair_2018["host"].extra},
    }
    truth_path = truth_dir / "F10.json"
    _write_json(truth_path, truth)
    return truth_path


def generate_large(fixture_id: str, out_dir: Path, truth_dir: Path) -> Path:
    target = F11_TARGET_ENTITIES if fixture_id == "F11" else F12_TARGET_ENTITIES
    rng = make_rng(fixture_id, "r2018")
    result = f11_large.build("R2018", rng, target_entities=target)
    path = out_dir / f"{fixture_id}.dxf"
    desc = _save_and_describe(result.doc, path)
    truth = {
        "fixture": fixture_id,
        "primary": desc,
        "totals": desc["stats"]["totals"],
        "extra": result.extra,
    }
    truth_path = truth_dir / f"{fixture_id}.json"
    _write_json(truth_path, truth)
    return truth_path


def generate(fixture_id: str, out_dir: Path, truth_dir: Path, large: bool) -> Path | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    if fixture_id == "F10":
        return generate_f10(out_dir, truth_dir)
    if fixture_id == "F12":
        if not large:
            return None
        return generate_large(fixture_id, out_dir, truth_dir)
    if fixture_id == "F11":
        return generate_large(fixture_id, out_dir, truth_dir)
    if fixture_id in SIMPLE_FIXTURES:
        return generate_simple(fixture_id, out_dir, truth_dir)
    raise ValueError(f"unknown fixture id: {fixture_id}")
