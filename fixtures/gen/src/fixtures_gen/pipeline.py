"""Generation pipeline: build one fixture's DXF variant(s), then independently
re-read the written bytes with ezdxf to compute truth statistics.

Truth layout (brief W2-03, replacing the pre-schema format documented in
git history of ``fixtures/README.md``):

* ``fixtures/truth/F##.json`` -- a ``LayerStatsDocument`` (schema:
  ``packages/schema/src/stats/layer-stats.schema.json``) computed on the
  fixture's primary R2018 file, and nothing else (the schema is closed --
  ``additionalProperties: false`` -- so no fixture bookkeeping fits here).
* ``fixtures/truth/F##.extra.json`` -- everything else: file descriptors for
  the primary and R2000/cp949 variant (including the variant's own
  full stats and its ``omitted`` note list), and the fixture-specific
  ground truth (member placements, table cells, level fields, gaps, XREF
  relationships, ...) previously nested under ``truth["extra"]``.
* F10 is a file *pair* (grid + host), so it produces two LayerStatsDocuments,
  ``F10_grid.json`` and ``F10_host.json``, plus one ``F10.extra.json``
  covering both.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.document import Drawing

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
from fixtures_gen.stats import compute_layer_stats

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


def _save_and_describe(doc: Drawing, path: Path) -> tuple[dict[str, Any], Drawing, str]:
    """Save ``doc``, re-read it, and return ``(descriptor, reread_doc, sha256)``.

    The descriptor never embeds full stats (see module docstring) -- callers
    that need them call :func:`fixtures_gen.stats.compute_layer_stats`
    themselves with the returned re-read document and sha256.
    """
    save(doc, path)
    reread = ezdxf.readfile(str(path))
    sha256 = _sha256(path)
    descriptor = {
        "file": path.name,
        "dxf_version": reread.dxfversion,
        "encoding": reread.encoding,
        "sha256": sha256,
        "size_bytes": path.stat().st_size,
    }
    return descriptor, reread, sha256


def generate_simple(fixture_id: str, out_dir: Path, truth_dir: Path) -> Path:
    module = SIMPLE_FIXTURES[fixture_id]

    rng_2018 = make_rng(fixture_id, "r2018")
    result_2018: BuildResult = module.build("R2018", rng_2018)
    primary_path = out_dir / f"{fixture_id}.dxf"
    primary_desc, primary_reread, primary_sha256 = _save_and_describe(result_2018.doc, primary_path)
    primary_stats = compute_layer_stats(primary_reread, file_sha256=primary_sha256)

    rng_2000 = make_rng(fixture_id, "r2000_cp949")
    result_2000: BuildResult = module.build("R2000", rng_2000)
    result_2000.doc.encoding = "cp949"
    variant_path = out_dir / f"{fixture_id}_r2000_cp949.dxf"
    variant_desc, variant_reread, variant_sha256 = _save_and_describe(result_2000.doc, variant_path)
    variant_stats = compute_layer_stats(variant_reread, file_sha256=variant_sha256)

    stats_path = truth_dir / f"{fixture_id}.json"
    _write_json(stats_path, primary_stats)

    extra = {
        "fixture": fixture_id,
        "primary": primary_desc,
        "variants": {
            "r2000_cp949": {**variant_desc, "omitted": result_2000.omitted, "stats": variant_stats}
        },
        "extra": result_2018.extra,
    }
    extra_path = truth_dir / f"{fixture_id}.extra.json"
    _write_json(extra_path, extra)
    return stats_path


def generate_f10(out_dir: Path, truth_dir: Path) -> Path:
    rng_2018 = make_rng("F10", "r2018")
    pair_2018 = f10_xref.build_pair("R2018", rng_2018)
    grid_path = out_dir / "F10_grid.dxf"
    host_path = out_dir / "F10_host.dxf"
    # grid must be written first: the host's XREF path is resolved relative
    # to the host file's directory, both live side by side in `out_dir`.
    grid_desc, grid_reread, grid_sha256 = _save_and_describe(pair_2018["grid"].doc, grid_path)
    host_desc, host_reread, host_sha256 = _save_and_describe(pair_2018["host"].doc, host_path)
    grid_stats = compute_layer_stats(grid_reread, file_sha256=grid_sha256)
    host_stats = compute_layer_stats(host_reread, file_sha256=host_sha256)

    rng_2000 = make_rng("F10", "r2000_cp949")
    pair_2000 = f10_xref.build_pair("R2000", rng_2000)
    pair_2000["grid"].doc.encoding = "cp949"
    pair_2000["host"].doc.encoding = "cp949"
    grid_r2000_path = out_dir / "F10_grid_r2000_cp949.dxf"
    host_r2000_path = out_dir / "F10_host_r2000_cp949.dxf"
    grid_r2000_desc, grid_r2000_reread, grid_r2000_sha256 = _save_and_describe(
        pair_2000["grid"].doc, grid_r2000_path
    )
    host_r2000_desc, host_r2000_reread, host_r2000_sha256 = _save_and_describe(
        pair_2000["host"].doc, host_r2000_path
    )
    grid_r2000_stats = compute_layer_stats(grid_r2000_reread, file_sha256=grid_r2000_sha256)
    host_r2000_stats = compute_layer_stats(host_r2000_reread, file_sha256=host_r2000_sha256)

    grid_stats_path = truth_dir / "F10_grid.json"
    host_stats_path = truth_dir / "F10_host.json"
    _write_json(grid_stats_path, grid_stats)
    _write_json(host_stats_path, host_stats)

    extra = {
        "fixture": "F10",
        "primary": {"grid": grid_desc, "host": host_desc},
        "variants": {
            "r2000_cp949": {
                "grid": {**grid_r2000_desc, "stats": grid_r2000_stats},
                "host": {**host_r2000_desc, "stats": host_r2000_stats},
            }
        },
        "extra": {"grid": pair_2018["grid"].extra, "host": pair_2018["host"].extra},
    }
    extra_path = truth_dir / "F10.extra.json"
    _write_json(extra_path, extra)
    return host_stats_path


def generate_large(fixture_id: str, out_dir: Path, truth_dir: Path) -> Path:
    target = F11_TARGET_ENTITIES if fixture_id == "F11" else F12_TARGET_ENTITIES
    rng = make_rng(fixture_id, "r2018")
    result = f11_large.build("R2018", rng, target_entities=target)
    path = out_dir / f"{fixture_id}.dxf"
    desc, reread, sha256 = _save_and_describe(result.doc, path)
    stats = compute_layer_stats(reread, file_sha256=sha256)

    stats_path = truth_dir / f"{fixture_id}.json"
    _write_json(stats_path, stats)

    extra = {"fixture": fixture_id, "primary": desc, "extra": result.extra}
    extra_path = truth_dir / f"{fixture_id}.extra.json"
    _write_json(extra_path, extra)
    return stats_path


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
