from __future__ import annotations

from pathlib import Path

import ezdxf

from halo_engine.ingest.dxf_loader import DIAG_DUPLICATE_HANDLE, load_dxf


def _write_minimal_dxf(path: Path, *, extra_entities_tags: str = "") -> None:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 4  # millimetres, matches the project convention
    doc.modelspace().add_line((0, 0), (10, 10))
    doc.saveas(str(path))
    if extra_entities_tags:
        text = path.read_text(encoding="utf-8")
        marker = "  0\nSECTION\n  2\nENTITIES\n"
        idx = text.index(marker) + len(marker)
        text = text[:idx] + extra_entities_tags + text[idx:]
        path.write_text(text, encoding="utf-8")


def test_load_dxf_reads_a_clean_file(tmp_path: Path) -> None:
    p = tmp_path / "clean.dxf"
    _write_minimal_dxf(p)

    result = load_dxf(p)

    assert result.recovered is False
    assert result.acadver == "AC1032"
    assert result.insunits == 4
    assert result.fingerprintguid is not None
    assert isinstance(result.audit_errors, list)
    assert result.audit_error_count == len(result.audit_errors)
    assert result.diagnostics == []
    lines = list(result.doc.modelspace().query("LINE"))
    assert len(lines) == 1


def test_load_dxf_diagnoses_a_duplicate_handle(tmp_path: Path) -> None:
    """A malformed producer writing two entities with the same handle (brief
    W3-08, G0 follow-up 2 -- observed on real acad-ts-written DXF) must not
    be silent stderr noise: ``load_dxf`` turns ezdxf's ``logger.warning``
    into a ``LoadResult.diagnostics`` entry instead. This is the *cause*;
    ``halo_engine.ingest.stats``'s ``dead-attrib`` diagnostic is the
    downstream *effect*, once ``Drawing.audit()`` fixes the collision up by
    destroying one of the two entities.
    """
    doc = ezdxf.new("R2018", setup=True)
    msp = doc.modelspace()
    line1 = msp.add_line((0, 0), (10, 10))
    line2 = msp.add_line((20, 20), (30, 30))
    duplicated_handle = line1.dxf.handle
    p = tmp_path / "dup_handle.dxf"
    doc.saveas(str(p))

    text = p.read_text(encoding="utf-8")
    target = f"  5\n{line2.dxf.handle}\n"
    assert text.count(target) == 1, "fixture setup must find line2's handle tag uniquely"
    text = text.replace(target, f"  5\n{duplicated_handle}\n", 1)
    p.write_text(text, encoding="utf-8")

    result = load_dxf(p)

    assert result.recovered is False
    dup_diags = [d for d in result.diagnostics if d["code"] == DIAG_DUPLICATE_HANDLE]
    assert dup_diags, f"expected a {DIAG_DUPLICATE_HANDLE} diagnostic, got {result.diagnostics}"
    assert dup_diags[0]["handle"] == duplicated_handle


def test_load_dxf_falls_back_to_recover_on_broken_structure(tmp_path: Path) -> None:
    """A missing ENDSEC (e.g. a drawing truncated mid-transfer) makes the
    strict ``ezdxf.readfile`` raise ``DXFStructureError``; ``load_dxf`` must
    catch that and hand off to the tolerant ``ezdxf.recover.readfile``,
    which still returns a usable (if incomplete) document.
    """
    p = tmp_path / "base.dxf"
    _write_minimal_dxf(p)
    text = p.read_text(encoding="utf-8")
    marker = "  0\nENDSEC\n  0\nSECTION\n  2\nOBJECTS\n"
    truncated = text[: text.index(marker)]
    broken = tmp_path / "broken.dxf"
    broken.write_text(truncated, encoding="utf-8")

    result = load_dxf(broken)

    assert result.recovered is True
    assert result.doc is not None


def test_load_dxf_audits_on_the_recover_path_too(tmp_path: Path) -> None:
    """``audit_errors``/``audit_error_count`` must come from a real
    ``Auditor`` on the recovery path exactly like on the strict path (both
    are plain lists of :class:`AuditIssue`, never ``None``).
    """
    p = tmp_path / "base.dxf"
    _write_minimal_dxf(p)
    text = p.read_text(encoding="utf-8")
    marker = "  0\nENDSEC\n  0\nSECTION\n  2\nOBJECTS\n"
    truncated = text[: text.index(marker)]
    broken = tmp_path / "broken.dxf"
    broken.write_text(truncated, encoding="utf-8")

    result = load_dxf(broken)

    assert result.recovered is True
    assert isinstance(result.audit_errors, list)
    assert result.audit_error_count == len(result.audit_errors)


def test_proxy_and_unsupported_entities_are_preserved(tmp_path: Path) -> None:
    """ezdxf preserves entity types it has no dedicated wrapper for
    (``DXFTagStorage``) rather than dropping them -- load_dxf must not lose
    them either, and they must round-trip through a save.
    """
    p = tmp_path / "proxy.dxf"
    injected = "  0\nHALO_UNKNOWN\n  5\nFFFF\n330\n17\n100\nAcDbEntity\n  8\n0\n"
    _write_minimal_dxf(p, extra_entities_tags=injected)

    result = load_dxf(p)
    types = [e.dxftype() for e in result.doc.modelspace()]
    assert "HALO_UNKNOWN" in types
    assert "LINE" in types

    out = tmp_path / "roundtrip.dxf"
    result.doc.saveas(str(out))
    assert "HALO_UNKNOWN" in out.read_text(encoding="utf-8")


def test_load_dxf_extracts_dwgcodepage_for_pre2007(tmp_path: Path) -> None:
    doc = ezdxf.new("R2000")
    doc.encoding = "cp949"
    doc.modelspace().add_text("안녕", dxfattribs={"layer": "0"})
    p = tmp_path / "r2000.dxf"
    doc.saveas(str(p))

    result = load_dxf(p)
    assert result.dwgcodepage == "ANSI_949"
    assert result.acadver == "AC1015"
