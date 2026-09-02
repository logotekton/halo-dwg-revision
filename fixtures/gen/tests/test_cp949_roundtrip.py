"""cp949 round trip: Korean TEXT/MTEXT content in the R2000 cp949 variants
must read back identical to what the generator wrote (brief's "Defaults for
ambiguity": ``doc.encoding = "cp949"`` before saving).
"""

from __future__ import annotations

import unicodedata

import ezdxf
import pytest
from conftest import GENERATED_DIR

from fixtures_gen.fixtures.f03_text import MTEXT_CONTENTS, TEXT_CONTENTS


def test_f03_text_roundtrips_through_cp949(generated_dir) -> None:
    path = generated_dir / "F03_r2000_cp949.dxf"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    doc = ezdxf.readfile(str(path))
    assert doc.encoding == "cp949"
    msp = doc.modelspace()

    texts = [e.dxf.text for e in msp.query("TEXT")]
    assert texts == TEXT_CONTENTS

    mtexts = [e.text for e in msp.query("MTEXT")]
    assert mtexts == MTEXT_CONTENTS


def test_f03_text_is_nfc_normalized(generated_dir) -> None:
    path = generated_dir / "F03_r2000_cp949.dxf"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    doc = ezdxf.readfile(str(path))
    for e in doc.modelspace().query("TEXT"):
        text = e.dxf.text
        assert text == unicodedata.normalize("NFC", text), f"not NFC: {text!r}"


_R2000_VARIANTS = (
    sorted(p.name for p in GENERATED_DIR.glob("*_r2000_cp949.dxf"))
    if GENERATED_DIR.exists()
    else []
)


@pytest.mark.parametrize("filename", _R2000_VARIANTS)
def test_no_mojibake_in_any_r2000_variant(filename: str, generated_dir) -> None:
    doc = ezdxf.readfile(str(generated_dir / filename))
    for e in doc.modelspace():
        if e.dxftype() == "TEXT":
            assert "�" not in e.dxf.text, f"{filename}: replacement char in {e.dxf.text!r}"
        elif e.dxftype() == "MTEXT":
            assert "�" not in e.text, f"{filename}: replacement char in {e.text!r}"
