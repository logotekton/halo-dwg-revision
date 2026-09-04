"""Re-reads every generated DXF with ezdxf (independent of the generator's
in-memory state) and checks that title-block frames are actually recognisable
per ``engine/src/halo_engine/compare/defaults/frames.yaml`` (R1-04's
contract, docs/contracts/r1.md SS5):

* the number of INSERTs carrying >= ``titleblock.min_attribs`` ATTRIBs on
  each side of a scenario equals the sheet count `truth.json` implies for
  that side (a sheet exists on the before side unless its status is
  `added`, on the after side unless its status is `removed`; a pair with
  `sheet_no: null`, i.e. S16's `unrecognized` file, contributes to neither).
* every such candidate carries at least one tag from each of
  ``number_tags``/``title_tags``/``scale_tags``/``date_tags``.

``frames.yaml``'s tag lists are read with a small regex rather than adding a
YAML dependency (the brief pins dev deps to pytest + jsonschema).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import ezdxf
import pytest

GEN_ROOT = Path(__file__).resolve().parents[1]
COMPARE_ROOT = GEN_ROOT.parent
REPO_ROOT = COMPARE_ROOT.parents[1]
FRAMES_YAML = REPO_ROOT / "engine" / "src" / "halo_engine" / "compare" / "defaults" / "frames.yaml"


def _scenario_dirs() -> list[Path]:
    return sorted(p for p in COMPARE_ROOT.iterdir() if p.is_dir() and p.name != "gen")


SCENARIO_DIRS = _scenario_dirs()


def _extract_tag_list(text: str, key: str) -> set[str]:
    m = re.search(rf"^\s*{re.escape(key)}:\s*\[(.*?)\]", text, re.MULTILINE)
    assert m, f"could not find `{key}` in {FRAMES_YAML}"
    return {t.strip().strip('"').strip("'") for t in m.group(1).split(",") if t.strip()}


def _extract_int(text: str, key: str) -> int:
    m = re.search(rf"^\s*{re.escape(key)}:\s*(\d+)", text, re.MULTILINE)
    assert m, f"could not find `{key}` in {FRAMES_YAML}"
    return int(m.group(1))


def _frames_yaml_text() -> str:
    assert FRAMES_YAML.is_file(), FRAMES_YAML
    return FRAMES_YAML.read_text(encoding="utf-8")


FRAMES_TEXT = _frames_yaml_text()
MIN_ATTRIBS = _extract_int(FRAMES_TEXT, "min_attribs")
NUMBER_TAGS = _extract_tag_list(FRAMES_TEXT, "number_tags")
TITLE_TAGS = _extract_tag_list(FRAMES_TEXT, "title_tags")
SCALE_TAGS = _extract_tag_list(FRAMES_TEXT, "scale_tags")
DATE_TAGS = _extract_tag_list(FRAMES_TEXT, "date_tags")


def _titleblock_candidates(doc) -> list:
    return [ins for ins in doc.modelspace().query("INSERT") if len(list(ins.attribs)) >= MIN_ATTRIBS]


def _count_titleblocks(dxf_dir: Path) -> int:
    total = 0
    for dxf_path in sorted(dxf_dir.glob("*.dxf")):
        doc = ezdxf.readfile(str(dxf_path))
        total += len(_titleblock_candidates(doc))
    return total


def _expected_side_counts(truth: dict) -> tuple[int, int]:
    before_n = after_n = 0
    for pair in truth["expected_pairs"]:
        if pair["sheet_no"] is None:
            continue
        if pair["status"] in ("same", "changed", "removed"):
            before_n += 1
        if pair["status"] in ("same", "changed", "added"):
            after_n += 1
    return before_n, after_n


def test_frames_yaml_tag_lists_are_non_empty() -> None:
    assert NUMBER_TAGS and "DWG_NO" in NUMBER_TAGS
    assert TITLE_TAGS and "TITLE" in TITLE_TAGS
    assert SCALE_TAGS and "SCALE" in SCALE_TAGS
    assert DATE_TAGS and "DATE" in DATE_TAGS
    assert MIN_ATTRIBS >= 1


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_titleblock_insert_count_matches_expected_sheets(scenario_dir: Path) -> None:
    truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
    before_expected, after_expected = _expected_side_counts(truth)

    before_actual = _count_titleblocks(scenario_dir / truth["before_dir"])
    after_actual = _count_titleblocks(scenario_dir / truth["after_dir"])

    assert before_actual == before_expected, f"{scenario_dir.name}: before side"
    assert after_actual == after_expected, f"{scenario_dir.name}: after side"


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_titleblock_attribs_match_frames_yaml_tags(scenario_dir: Path) -> None:
    for dxf_path in sorted(scenario_dir.rglob("*.dxf")):
        doc = ezdxf.readfile(str(dxf_path))
        for ins in _titleblock_candidates(doc):
            tags = {a.dxf.tag for a in ins.attribs}
            assert tags & NUMBER_TAGS, f"{dxf_path}: no number_tags match among {tags}"
            assert tags & TITLE_TAGS, f"{dxf_path}: no title_tags match among {tags}"
            assert tags & SCALE_TAGS, f"{dxf_path}: no scale_tags match among {tags}"
            assert tags & DATE_TAGS, f"{dxf_path}: no date_tags match among {tags}"
