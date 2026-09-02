from __future__ import annotations

from pathlib import Path

import ezdxf

from halo_engine.ingest.encoding import (
    decode_escapes,
    load_with_corrected_encoding,
    mojibake_score,
    resolve_codepage,
)


def _cp949_doc_with_wrong_declared_codepage(tmp_path: Path, text: str) -> Path:
    """A file whose *bytes* are cp949 but whose ``$DWGCODEPAGE`` header
    claims ANSI_1252 -- the mis-declaration :func:`resolve_codepage` must
    correct.
    """
    doc = ezdxf.new("R2000")
    doc.encoding = "cp949"
    doc.modelspace().add_text(text, dxfattribs={"layer": "0"})
    correct = tmp_path / "correct.dxf"
    doc.saveas(str(correct))
    raw = correct.read_bytes()
    patched = raw.replace(b"ANSI_949", b"ANSI_1252")
    assert patched != raw, "fixture must actually declare a different codepage than it's saved in"
    mislabeled = tmp_path / "mislabeled.dxf"
    mislabeled.write_bytes(patched)
    return mislabeled


def test_mojibake_score_prefers_korean_over_latin1_supplement() -> None:
    korean = mojibake_score("안녕하세요 반갑습니다")
    mojibake = mojibake_score("¾È³çÇÏ¼¼¿ä ¹Ý°©½À´Ï´Ù")
    assert korean > 0
    assert mojibake < 0
    assert korean > mojibake


def test_mojibake_score_empty_text_is_neutral() -> None:
    assert mojibake_score("") == 0.0


def test_decode_escapes_handles_unicode_and_mif() -> None:
    assert decode_escapes(r"\U+AC00") == "가"
    # MIF code "3" -> cp949 (Wansung); 0xAC00 as cp949 bytes is b"\xb0\xa1" ("가").
    mif = r"\M+3" + b"\xb0\xa1".hex().upper()
    assert decode_escapes(mif) == "가"


def test_resolve_codepage_r2007_plus_is_always_utf8(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018", setup=True)
    doc.modelspace().add_text("안녕", dxfattribs={"layer": "0"})
    p = tmp_path / "r2018.dxf"
    doc.saveas(str(p))

    resolution = resolve_codepage(str(p))
    assert resolution.codepage_effective == "UTF-8"
    assert resolution.retried is False
    assert resolution.codepage_declared is None


def test_resolve_codepage_correctly_declared_cp949_is_kept(tmp_path: Path) -> None:
    doc = ezdxf.new("R2000")
    doc.encoding = "cp949"
    doc.modelspace().add_text("안녕하세요", dxfattribs={"layer": "0"})
    p = tmp_path / "cp949.dxf"
    doc.saveas(str(p))

    resolution = resolve_codepage(str(p))
    assert resolution.codepage_effective == "cp949"
    assert resolution.codepage_declared == "ANSI_949"


def test_resolve_codepage_retries_and_corrects_mislabeled_codepage(tmp_path: Path) -> None:
    mislabeled = _cp949_doc_with_wrong_declared_codepage(tmp_path, "안녕하세요 반갑습니다")

    resolution = resolve_codepage(str(mislabeled))
    assert resolution.codepage_declared == "ANSI_1252"
    assert resolution.codepage_effective == "cp949"
    assert resolution.retried is True
    assert resolution.retry_score is not None
    assert resolution.declared_score is not None
    assert resolution.retry_score > resolution.declared_score


def test_load_with_corrected_encoding_actually_fixes_the_text(tmp_path: Path) -> None:
    mislabeled = _cp949_doc_with_wrong_declared_codepage(tmp_path, "안녕하세요 반갑습니다")

    load_result, resolution = load_with_corrected_encoding(str(mislabeled))
    text = next(iter(load_result.doc.modelspace().query("TEXT"))).dxf.text
    assert text == "안녕하세요 반갑습니다"
    assert resolution.codepage_effective == "cp949"


def test_f03_r2018_and_cp949_variant_have_the_same_text_set(generated_dir: Path) -> None:
    """F03 cp949 변형 -> R2018 변형과 텍스트 집합 동일 (brief Constraints)."""

    def text_set(path: Path) -> set[str]:
        load_result, _ = load_with_corrected_encoding(str(path))
        texts: set[str] = set()
        for e in load_result.doc.modelspace():
            if e.dxftype() == "TEXT":
                texts.add(e.dxf.text)
            elif e.dxftype() == "MTEXT":
                texts.add(e.text)
        return texts

    primary = text_set(generated_dir / "F03.dxf")
    variant = text_set(generated_dir / "F03_r2000_cp949.dxf")
    assert primary == variant
    assert primary, "expected at least one TEXT/MTEXT string in F03"
