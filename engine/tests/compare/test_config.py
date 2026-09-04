"""``compare/config.py`` -- the defaults, the copy, the overlay and the failures.

The numbers asserted here are the interview ledger's, quoted through
``docs/contracts/r1.md`` §5. They are pinned in a test rather than only in a
YAML comment because every later rule multiplies them: a silent change to
``cloud.arc`` or ``minor.move_tolerance`` would show up as "the clouds look
wrong" three tasks away.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from halo_engine.bundle.create import BundleHandle
from halo_engine.bundle.layout import BundleLayout
from halo_engine.compare import config as config_module
from halo_engine.compare.config import (
    DEFAULT_COMPARE_YAML,
    DEFAULT_FRAMES_YAML,
    CompareConfig,
    CompareConfigError,
    load_compare_config,
    load_frames_config,
    scale_factor,
)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class TestDefaults:
    def test_first_load_copies_both_files_into_the_bundle(
        self, compare_bundle: BundleHandle
    ) -> None:
        layout = compare_bundle.layout
        assert not layout.compare_yaml.exists()
        assert not layout.frames_yaml.exists()

        load_compare_config(compare_bundle)
        load_frames_config(compare_bundle)

        # Copied verbatim: the comments are the documentation the site engineer reads.
        assert layout.compare_yaml.read_bytes() == DEFAULT_COMPARE_YAML.read_bytes()
        assert layout.frames_yaml.read_bytes() == DEFAULT_FRAMES_YAML.read_bytes()

    def test_the_defaults_are_the_ledger_values(self, compare_bundle: BundleHandle) -> None:
        config = load_compare_config(compare_bundle)

        assert config.schema_version == "0.1"
        assert config.ingest.ignore_patterns == ["*_recover.dwg", "*.bak", "*.dwl", "*.dwl2"]
        assert config.ingest.converter == "auto"
        assert config.ingest.zwcad_timeout_s == 120
        assert config.ingest.zwcad_dxf_version == "2013"
        assert config.ingest.crosscheck_sample == 5

        assert config.match.fingerprint_tolerance == 1.0
        assert config.match.title_jaccard_min == 0.6

        assert config.minor.move_tolerance == 0.01
        assert config.minor.fold == [
            "layer_only",
            "color_only",
            "linetype_only",
            "lineweight_only",
            "hatch_regen",
            "dim_regen",
            "mtext_format_only",
        ]

        assert config.cluster.grow_ratio == 0.02
        assert config.cluster.grow_min == 300

        assert config.cloud.layer_prefix == "REV-"
        assert config.cloud.color == 1
        assert config.cloud.margin == 50
        assert config.cloud.arc == 100
        assert config.cloud.arc_bulge == 0.5
        assert config.cloud.badge_side == 200
        assert config.cloud.badge_text_height == 90
        assert config.cloud.badge_anchor == "top_right"

        assert config.revtable.columns == ["번호", "내용", "일자"]
        assert config.revtable.col_widths == [800, 6000, 2000]
        assert config.revtable.row_height == 400
        assert config.revtable.text_height == 250
        assert config.revtable.anchor == "titleblock_left"

        assert config.output.dir_name == "출력"
        assert config.output.file_pattern == "{sheet_no}_{after_label}_markup"
        assert config.output.dwg_writer == "auto"

    def test_frames_defaults_are_the_contract_values(self, compare_bundle: BundleHandle) -> None:
        frames = load_frames_config(compare_bundle)

        assert frames.schema_version == "0.1"
        assert frames.titleblock.min_attribs == 3
        assert frames.titleblock.number_tags[:3] == ["DWG_NO", "DWGNO", "DWG-NO"]
        assert "도면번호" in frames.titleblock.number_tags
        assert frames.titleblock.title_tags[0] == "TITLE"
        assert frames.titleblock.scale_tags == ["SCALE", "SCL", "축척"]
        assert frames.titleblock.date_tags == ["DATE", "일자", "날짜"]
        assert frames.titleblock.fallback_most_common_block is True
        assert frames.titleblock.block_name_patterns == []

        assert frames.frame.boundary == "smallest_enclosing_rect"
        assert frames.frame.fallback == "modal_size_titleblock_bottom_right"
        assert frames.frame.assign == "bbox_center"

        assert frames.normalize.strip_spaces is True
        assert frames.normalize.fullwidth_to_ascii is True
        assert frames.normalize.upper is True
        assert frames.normalize.unify_hyphen is True

    def test_loading_twice_neither_rewrites_nor_changes_anything(
        self, compare_bundle: BundleHandle
    ) -> None:
        first = load_compare_config(compare_bundle)
        stamp = compare_bundle.layout.compare_yaml.stat().st_mtime_ns
        second = load_compare_config(compare_bundle)

        assert first == second
        assert compare_bundle.layout.compare_yaml.stat().st_mtime_ns == stamp


class TestProjectOverrides:
    def test_a_partial_file_only_overrides_the_keys_it_names(
        self, compare_bundle: BundleHandle
    ) -> None:
        _write(
            compare_bundle.layout.compare_yaml,
            "minor:\n  move_tolerance: 0.5\ncloud:\n  color: 3\n",
        )
        config = load_compare_config(compare_bundle)

        assert config.minor.move_tolerance == 0.5
        assert config.cloud.color == 3
        # Everything the file did not mention is still the packaged default.
        assert config.minor.fold[0] == "layer_only"
        assert config.cloud.arc == 100
        assert config.output.dir_name == "출력"
        assert config.schema_version == "0.1"

    def test_an_existing_file_is_never_overwritten_by_the_defaults(
        self, compare_bundle: BundleHandle
    ) -> None:
        text = "cloud:\n  margin: 25\n"
        _write(compare_bundle.layout.compare_yaml, text)
        load_compare_config(compare_bundle)
        assert compare_bundle.layout.compare_yaml.read_text(encoding="utf-8") == text

    def test_a_list_replaces_rather_than_extends(self, compare_bundle: BundleHandle) -> None:
        # A shortened ignore list has to be expressible; appending behind the
        # user's back would make "stop skipping .bak" impossible.
        _write(compare_bundle.layout.compare_yaml, 'ingest:\n  ignore_patterns: ["*.bak"]\n')
        config = load_compare_config(compare_bundle)
        assert config.ingest.ignore_patterns == ["*.bak"]

    def test_an_empty_file_falls_back_to_every_default(self, compare_bundle: BundleHandle) -> None:
        _write(compare_bundle.layout.compare_yaml, "")
        assert load_compare_config(compare_bundle).cloud.arc == 100

    def test_frames_overrides_merge_the_same_way(self, compare_bundle: BundleHandle) -> None:
        _write(
            compare_bundle.layout.frames_yaml,
            'titleblock:\n  min_attribs: 5\n  block_name_patterns: ["TITLE*"]\n',
        )
        frames = load_frames_config(compare_bundle)
        assert frames.titleblock.min_attribs == 5
        assert frames.titleblock.block_name_patterns == ["TITLE*"]
        assert frames.normalize.upper is True


class TestFailures:
    def test_an_unknown_key_names_the_file_and_the_key(self, compare_bundle: BundleHandle) -> None:
        _write(compare_bundle.layout.compare_yaml, "cloud:\n  arc_length: 120\n")
        with pytest.raises(CompareConfigError) as excinfo:
            load_compare_config(compare_bundle)

        error = excinfo.value
        assert error.path == compare_bundle.layout.compare_yaml
        assert "compare.yaml" in str(error)
        assert str(compare_bundle.layout.compare_yaml) in str(error)
        assert any("arc_length" in reason for reason in error.reasons)

    def test_a_wrong_type_is_refused(self, compare_bundle: BundleHandle) -> None:
        _write(compare_bundle.layout.compare_yaml, 'minor:\n  move_tolerance: "조금"\n')
        with pytest.raises(CompareConfigError) as excinfo:
            load_compare_config(compare_bundle)
        assert any("minor.move_tolerance" in reason for reason in excinfo.value.reasons)

    def test_a_fold_reason_outside_the_contract_is_refused(
        self, compare_bundle: BundleHandle
    ) -> None:
        _write(compare_bundle.layout.compare_yaml, "minor:\n  fold: [layer_only, almost_same]\n")
        with pytest.raises(CompareConfigError):
            load_compare_config(compare_bundle)

    def test_a_column_without_a_width_is_refused(self, compare_bundle: BundleHandle) -> None:
        # Adding a 담당 column and forgetting its width would otherwise only show
        # up as a crooked table on a printed drawing.
        _write(
            compare_bundle.layout.compare_yaml,
            'revtable:\n  columns: ["번호", "내용", "일자", "담당"]\n',
        )
        with pytest.raises(CompareConfigError) as excinfo:
            load_compare_config(compare_bundle)
        assert any("col_widths" in reason for reason in excinfo.value.reasons)

    def test_broken_yaml_is_refused_with_the_parser_message(
        self, compare_bundle: BundleHandle
    ) -> None:
        _write(compare_bundle.layout.compare_yaml, "cloud:\n  arc: [1, 2\n")
        with pytest.raises(CompareConfigError) as excinfo:
            load_compare_config(compare_bundle)
        assert any("YAML syntax" in reason for reason in excinfo.value.reasons)

    def test_a_top_level_list_is_refused(self, compare_bundle: BundleHandle) -> None:
        _write(compare_bundle.layout.frames_yaml, "- titleblock\n")
        with pytest.raises(CompareConfigError) as excinfo:
            load_frames_config(compare_bundle)
        assert any("mapping" in reason for reason in excinfo.value.reasons)

    def test_a_config_object_cannot_be_mutated_by_accident(
        self, compare_bundle: BundleHandle
    ) -> None:
        config = load_compare_config(compare_bundle)
        with pytest.raises(ValidationError):
            config.cloud.arc = 200  # type: ignore[misc]


class TestAcceptedArguments:
    def test_the_loaders_take_a_handle_a_layout_or_a_path(
        self, compare_bundle: BundleHandle, project_dir: Path
    ) -> None:
        from_handle = load_compare_config(compare_bundle)
        from_layout = load_compare_config(compare_bundle.layout)
        from_path = load_compare_config(project_dir / ".halo")
        from_str = load_compare_config(str(project_dir / ".halo"))
        assert from_handle == from_layout == from_path == from_str

    def test_a_bare_layout_on_a_fresh_directory_creates_the_files(self, tmp_path: Path) -> None:
        layout = BundleLayout(tmp_path / "empty.halo")
        config = load_compare_config(layout)
        assert isinstance(config, CompareConfig)
        assert layout.compare_yaml.is_file()

    def test_something_that_is_not_a_bundle_is_rejected(self) -> None:
        with pytest.raises(TypeError):
            load_compare_config(object())  # type: ignore[arg-type]


class TestScaleFactor:
    @pytest.mark.parametrize(
        ("denominator", "expected"),
        [(50, 0.5), (100, 1.0), (200, 2.0), (1200, 12.0), (None, 1.0), (0, 1.0), (-50, 1.0)],
    )
    def test_scale_factor(self, denominator: int | None, expected: float) -> None:
        assert scale_factor(denominator) == pytest.approx(expected)


class TestRevisionLayer:
    def test_layer_name_is_the_prefix_plus_the_compact_run_date(
        self, compare_bundle: BundleHandle
    ) -> None:
        config = load_compare_config(compare_bundle)
        assert config.revision_layer("2026-09-04") == "REV-20260904"
        # The compare DXF has no suffix; a second export of the same day does.
        assert config.revision_layer("2026-09-04", suffix=1) == "REV-20260904"
        assert config.revision_layer("2026-09-04", suffix=2) == "REV-20260904-2"


def test_config_module_stays_free_of_ezdxf() -> None:
    """Reading settings must not drag the DXF stack into the API process."""
    source = Path(config_module.__file__).read_text(encoding="utf-8")
    assert "import ezdxf" not in source
    assert "from ezdxf" not in source
