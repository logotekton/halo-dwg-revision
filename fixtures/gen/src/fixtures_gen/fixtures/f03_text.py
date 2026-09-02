"""F03 -- Korean TEXT/MTEXT with varied rotation/alignment, two text styles,
and special characters ("%%d", "Ø", "㎡").

Style ``KOR-BIG``  references ``romans.shx`` + big-font ``whgtxt.shx`` (the
classic AutoCAD-for-Korean SHX big-font setup).
Style ``KOR-TTF``  references a TrueType font (``malgun.ttf``, Malgun Gothic).
Neither font file is shipped -- the style only needs to *reference* the name,
per the brief's "Defaults for ambiguity".
"""

from __future__ import annotations

import random

from ezdxf.enums import TextEntityAlignment

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc

TEXT_ALIGNMENTS = [
    TextEntityAlignment.LEFT,
    TextEntityAlignment.CENTER,
    TextEntityAlignment.RIGHT,
    TextEntityAlignment.TOP_LEFT,
    TextEntityAlignment.TOP_CENTER,
    TextEntityAlignment.TOP_RIGHT,
    TextEntityAlignment.MIDDLE_LEFT,
    TextEntityAlignment.MIDDLE_CENTER,
    TextEntityAlignment.MIDDLE_RIGHT,
    TextEntityAlignment.BOTTOM_LEFT,
    TextEntityAlignment.BOTTOM_CENTER,
    TextEntityAlignment.BOTTOM_RIGHT,
]

ROTATIONS = [0, 15, 30, 45, 90, 135, 180, 225, 270, 315]

TEXT_CONTENTS = [
    "거실",
    "침실1",
    "침실2",
    "주방",
    "욕실",
    "다용도실",
    "발코니",
    "현관",
    "%%d500 배관",
    "Ø300 PIT",
    "면적 84.5㎡",
    "C1 600x600",
    "G1 400x600",
    "B1 300x500",
    "S-101",
    "2층 구조평면도",
    "축척 1/100",
    "2FL SL+3,300",
    "EL.+0.000",
    "단위 ㎡ 표기",
]

MTEXT_CONTENTS = [
    "실명: 거실\\P면적: 23.4㎡",
    "실명: 침실1\\P면적: 12.1㎡\\P비고: -",
    "배관 Ø100\\P구배 1/100",
    "단면 표기\\PC1 600x600\\PG1 400x600",
    "층고표\\PSL+3,300\\PCH 2,600",
    "특기사항\\P1. 모든 치수는 mm 단위\\P2. Ø는 지름 기호",
    "면적표\\P전용 84.5㎡\\P공용 12.3㎡\\P합계 96.8㎡",
    "구조평면도\\P축척 1/100\\P도면번호 S-101",
    "비고\\P%%d 는 지름을 뜻함",
    "완료\\P검토자 확인 요망",
]


def _make_styles(doc) -> None:
    if "KOR-BIG" not in doc.styles:
        doc.styles.new("KOR-BIG", dxfattribs={"font": "romans.shx", "bigfont": "whgtxt.shx"})
    if "KOR-TTF" not in doc.styles:
        doc.styles.new("KOR-TTF", dxfattribs={"font": "malgun.ttf"})


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, ["A-TEXT"])
    _make_styles(doc)
    msp = doc.modelspace()

    cols = 5
    spacing_x = 3000.0
    spacing_y = 900.0

    for i, content in enumerate(TEXT_CONTENTS):
        row, col = divmod(i, cols)
        x, y = col * spacing_x, -row * spacing_y
        style = "KOR-BIG" if i % 2 == 0 else "KOR-TTF"
        height = [100, 120, 150][i % 3]
        rotation = ROTATIONS[i % len(ROTATIONS)]
        align = TEXT_ALIGNMENTS[i % len(TEXT_ALIGNMENTS)]
        t = msp.add_text(
            content,
            dxfattribs={
                "layer": "A-TEXT",
                "style": style,
                "height": height,
                "rotation": rotation,
            },
        )
        t.set_placement((x, y), align=align)

    mtext_y0 = -spacing_y * ((len(TEXT_CONTENTS) + cols - 1) // cols) - 1500.0
    for i, content in enumerate(MTEXT_CONTENTS):
        row, col = divmod(i, 3)
        x = col * 4500.0
        y = mtext_y0 - row * 2200.0
        style = "KOR-BIG" if i % 2 == 0 else "KOR-TTF"
        msp.add_mtext(
            content,
            dxfattribs={
                "layer": "A-TEXT",
                "style": style,
                "char_height": 110,
                "width": 3800,
                "insert": (x, y),
            },
        )

    extra = {
        "text_count_expected": len(TEXT_CONTENTS),
        "mtext_count_expected": len(MTEXT_CONTENTS),
        "special_characters": ["%%d", "Ø", "㎡"],
        "styles": ["KOR-BIG", "KOR-TTF"],
    }
    return BuildResult(doc=doc, extra=extra)
