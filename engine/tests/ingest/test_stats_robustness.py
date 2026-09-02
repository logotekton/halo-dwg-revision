"""Robustness regression tests (brief W3-08 goal 1, G0 follow-up 2).

``compute_layer_stats`` must turn two malformations into a ``diagnostics[]``
entry and keep going, never an uncaught exception -- see the "Robustness"
section of ``engine/src/halo_engine/ingest/stats.py``'s module docstring for
the full mechanism of each:

* a dead ATTRIB (``is_alive is False``) still referenced by its owning
  INSERT's ``attribs``;
* a zero-length OCS/direction vector (e.g. an MTEXT ``text_direction`` of
  ``(0, 0, 0)``).

Both are reproduced two ways: a hermetic synthetic file (fast, deterministic,
exercises the exact guarded code path regardless of environment) and the
real ``acad-ts``-written ``F06.dxf``/``F03.dxf`` the brief names, obtained by
round-tripping the DWG fixtures through ``packages/acad-bridge``'s
``dwg2dxf`` CLI -- skipped when that CLI has not been built (``pnpm --filter
@halo-cad/acad-bridge build``), since a bare ``cd engine && uv run pytest``
checkout has no Node toolchain guarantee.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import ezdxf
import pytest

from halo_engine.ingest.dxf_loader import load_dxf
from halo_engine.ingest.stats import (
    DIAG_DEAD_ATTRIB,
    DIAG_UNEXPECTED_OWNED_ENTITY,
    DIAG_ZERO_LENGTH_OCS_VECTOR,
    compute_layer_stats,
)

# engine/tests/ingest/test_stats_robustness.py -> engine/tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
ACAD_BRIDGE_BIN = REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Hermetic synthetic reproductions
# ---------------------------------------------------------------------------


def test_dead_attrib_in_insert_attribs_is_diagnosed_not_raised(tmp_path: Path) -> None:
    """Manufacture the exact precondition (``is_alive is False``) directly.

    Real files reach this state through a duplicate DXF handle: ezdxf's own
    ``Drawing.audit()`` destroys one of the two entities sharing a handle,
    but an owning INSERT's ``attribs`` list still references the destroyed
    object (module docstring). The unit test does not need to recreate the
    duplicate-handle mechanism -- only the state it leaves behind -- so it
    calls ``.destroy()`` directly, the same effect ``audit()`` has.
    """
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    block = doc.blocks.new("TAGBLK")
    block.add_attdef("TAG", (0, 0), dxfattribs={"height": 2.5})
    insert = msp.add_blockref("TAGBLK", (0, 0), dxfattribs={"layer": "X-GRID"})
    attrib = insert.add_attrib("TAG", "hello", (0, 0), dxfattribs={"layer": "A-TEXT"})
    insert_handle = insert.dxf.handle

    attrib.destroy()
    assert not attrib.is_alive
    assert insert.attribs[0] is attrib, "the dead object must still be reachable via attribs"

    diagnostics: list[dict] = []
    result = compute_layer_stats(doc, file_sha256="0" * 64, diagnostics=diagnostics)

    dead_diags = [d for d in diagnostics if d["code"] == DIAG_DEAD_ATTRIB]
    assert dead_diags, f"expected a {DIAG_DEAD_ATTRIB} diagnostic, got {diagnostics}"
    assert all(d.get("handle") == insert_handle for d in dead_diags)
    # Not double counted, and the dead ATTRIB's text never reaches text_hash.
    assert "ATTRIB" not in result["totals"]["count_by_type"]
    assert result["totals"]["count_by_type"] == {"INSERT": 1}
    assert result["totals"]["text_count"] == 0


def test_zero_length_mtext_direction_is_diagnosed_not_raised(tmp_path: Path) -> None:
    """An MTEXT ``text_direction`` of ``(0, 0, 0)``, loaded as ezdxf loads it.

    ezdxf's typed setter refuses a zero vector (``validator=is_not_null_vector,
    fixer=RETURN_DEFAULT``), so this cannot be built through the normal API --
    it has to be written to disk and re-read, because MTEXT attributes load
    through ``fast_load_dxfattribs``, which bypasses that validator (module
    docstring).
    """
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    mtext = msp.add_mtext("hello", dxfattribs={"insert": (0, 0, 0), "layer": "A-TEXT"})
    mtext.dxf.text_direction = (1, 0, 0)  # written as group 11/21/31
    p = tmp_path / "mtext_zero.dxf"
    doc.saveas(str(p))

    text = p.read_text(encoding="utf-8")
    marker = "\nhello\n"
    idx = text.index(marker) + len(marker)
    # Force the direction vector to zero length -- past what the typed API allows.
    text = text[:idx] + "11\n0.0\n21\n0.0\n31\n0.0\n" + text[idx:]
    p.write_text(text, encoding="utf-8")

    reloaded = ezdxf.readfile(str(p))
    reloaded_mtext = next(iter(reloaded.modelspace().query("MTEXT")))
    assert tuple(reloaded_mtext.dxf.text_direction) == (0.0, 0.0, 0.0), (
        "fixture setup must actually produce the zero vector, not exercise the validator"
    )

    diagnostics: list[dict] = []
    result = compute_layer_stats(reloaded, file_sha256=_sha256_of(p), diagnostics=diagnostics)

    zero_vector_diags = [d for d in diagnostics if d["code"] == DIAG_ZERO_LENGTH_OCS_VECTOR]
    assert zero_vector_diags, f"expected a {DIAG_ZERO_LENGTH_OCS_VECTOR} diagnostic"
    assert result["totals"]["count_by_type"] == {"MTEXT": 1}
    # bbox is best-effort: excluded because the only entity's bbox failed.
    a_text_bucket = next(b for b in result["buckets"] if b["layer"] == "A-TEXT")
    assert "bbox" not in a_text_bucket["aggregate"]


def test_seqend_at_top_level_is_diagnosed_and_excluded(tmp_path: Path) -> None:
    """stats-definition.md: ATTRIB/SEQEND/VERTEX are never counted at the top
    level (they belong to their owning entity) -- even if a malformed
    producer hands one to the layout iterator directly (observed on acad-ts
    DXF output, see the acad-ts round-trip tests below).
    """
    doc = ezdxf.new("R2018", setup=True)
    doc.modelspace().add_line((0, 0), (10, 10), dxfattribs={"layer": "0"})
    p = tmp_path / "stray_seqend.dxf"
    doc.saveas(str(p))

    text = p.read_text(encoding="utf-8")
    marker = "  0\nSECTION\n  2\nENTITIES\n"
    idx = text.index(marker) + len(marker)
    stray_seqend = "  0\nSEQEND\n  5\nFF\n  8\n0\n"
    text = text[:idx] + stray_seqend + text[idx:]
    p.write_text(text, encoding="utf-8")

    doc2 = ezdxf.readfile(str(p))
    types = {e.dxftype() for e in doc2.modelspace()}
    assert "SEQEND" in types, "fixture setup must actually put a stray SEQEND at top level"

    diagnostics: list[dict] = []
    result = compute_layer_stats(doc2, file_sha256=_sha256_of(p), diagnostics=diagnostics)

    unexpected = [d for d in diagnostics if d["code"] == DIAG_UNEXPECTED_OWNED_ENTITY]
    assert unexpected, f"expected a {DIAG_UNEXPECTED_OWNED_ENTITY} diagnostic"
    assert "SEQEND" not in result["totals"]["count_by_type"]
    assert result["totals"]["count_by_type"] == {"LINE": 1}


# ---------------------------------------------------------------------------
# Real acad-ts-written DXF (brief: "acad-ts 산출 DXF F06/F03으로 회귀 테스트")
# ---------------------------------------------------------------------------


def _acad_written_dxf(tmp_path: Path, generated_dir: Path, name: str) -> Path:
    if not ACAD_BRIDGE_BIN.exists() or shutil.which("node") is None:
        pytest.skip(
            "packages/acad-bridge/bin/acad-bridge.mjs not built -- run "
            "`pnpm --filter @halo-cad/acad-bridge build` (needs Node, not part of a "
            "bare `cd engine && uv run pytest` checkout)"
        )
    src = generated_dir / f"{name}.dwg"
    if not src.exists():
        pytest.skip(f"{src} missing -- run `cd fixtures/gen && uv run python -m fixtures_gen`")
    out = tmp_path / f"{name}.acad.dxf"
    subprocess.run(
        ["node", str(ACAD_BRIDGE_BIN), "dwg2dxf", str(src), str(out)],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
        text=True,
    )
    return out


def test_f06_acad_ts_dxf_no_exception_and_diagnostics_listed(
    tmp_path: Path, generated_dir: Path
) -> None:
    """Acceptance check: ``halo-engine stats`` on acad-ts-written F06 must not
    raise, and must list the dead-ATTRIB diagnostic (acad-bridge README
    "Known acad-ts gaps" #1: F06's ``X-TITLE`` layer/block name collision
    makes acad-ts drop and duplicate-handle its own INSERT/ATTRIB output).
    """
    out = _acad_written_dxf(tmp_path, generated_dir, "F06")
    load_result = load_dxf(out)

    diagnostics: list[dict] = []
    result = compute_layer_stats(
        load_result.doc, file_sha256=_sha256_of(out), diagnostics=diagnostics
    )

    assert diagnostics, "F06's known acad-ts gaps must produce at least one diagnostic"
    codes = {d["code"] for d in diagnostics}
    assert codes & {DIAG_DEAD_ATTRIB, DIAG_UNEXPECTED_OWNED_ENTITY}
    assert result["totals"]["entity_count"] > 0


def test_f03_acad_ts_dxf_no_exception_and_diagnostics_listed(
    tmp_path: Path, generated_dir: Path
) -> None:
    """Same acceptance check for F03: acad-ts's MTEXT writer round trip is
    the source of the zero-length ``text_direction`` vector.
    """
    out = _acad_written_dxf(tmp_path, generated_dir, "F03")
    load_result = load_dxf(out)

    diagnostics: list[dict] = []
    result = compute_layer_stats(
        load_result.doc, file_sha256=_sha256_of(out), diagnostics=diagnostics
    )

    assert diagnostics, "F03's known acad-ts gaps must produce at least one diagnostic"
    assert any(d["code"] == DIAG_ZERO_LENGTH_OCS_VECTOR for d in diagnostics)
    assert result["totals"]["entity_count"] > 0
