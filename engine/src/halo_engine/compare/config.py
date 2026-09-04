"""``compare.yaml`` and ``frames.yaml``: the values every comparison rule reads.

The two files are the seam between "what the ledger decided" and "what this
project needs". The defaults next to this module are the ledger's numbers --
0.01mm for a negligible move, 1mm fingerprint matching, a 100mm arc, a 200mm
badge (``docs/contracts/r1.md`` §5) -- and they are *copied* into the bundle the
first time a project is compared, comments and all, so a site engineer can open
``.halo/compare.yaml`` and change one number without knowing anything about the
engine. Loading merges the project's file over the defaults key by key, which
means a copy that was written by an older version, or that has had a section
deleted, still yields a complete configuration instead of a ``KeyError`` deep
inside the diff.

Deliberately light: pyyaml and pydantic only. Reading settings must not pull in
ezdxf, because the API process asks for them on requests that never open a
drawing. Nothing here reads the clock or the random generator either -- the
copy is byte-for-byte the packaged default (CLAUDE.md rule 6).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from halo_engine.bundle.layout import BundleLayout

#: The packaged defaults, shipped as package data (``[tool.hatch.build]``
#: includes everything under ``src/halo_engine``).
DEFAULTS_DIR = Path(__file__).parent / "defaults"
DEFAULT_COMPARE_YAML = DEFAULTS_DIR / "compare.yaml"
DEFAULT_FRAMES_YAML = DEFAULTS_DIR / "frames.yaml"

#: Contract version of both files. Bumped only with the schemas.
CONFIG_SCHEMA_VERSION = "0.1"

#: `1:100` is the reference scale every length in `cloud` and `revtable` is
#: written at; a sheet at another scale multiplies by `scale_factor`.
REFERENCE_SCALE_DENOMINATOR = 100

MinorFoldReason = Literal[
    "move_le_0_01",
    "layer_only",
    "color_only",
    "linetype_only",
    "lineweight_only",
    "hatch_regen",
    "dim_regen",
    "mtext_format_only",
]


class CompareConfigError(ValueError):
    """A settings file could not be read, naming the file and why.

    Carries the ``path`` so a router can tell the user which file to open --
    these are files people edit by hand, so "somewhere in your settings" is not
    a good enough answer.
    """

    def __init__(self, path: Path, reasons: list[str]) -> None:
        detail = "; ".join(reasons) if reasons else "unreadable"
        super().__init__(f"{path.name} is not valid ({path}): {detail}")
        self.path = path
        self.reasons = reasons


class _Section(BaseModel):
    """Base for every settings block: unknown keys are an error, values are read-only.

    ``extra="forbid"`` is the point of the class. A typo in a hand-edited file
    would otherwise be silently ignored and the default would keep applying,
    which looks exactly like "my change did nothing".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class IngestSettings(_Section):
    """How the two set folders become working DXFs."""

    ignore_patterns: list[str] = Field(
        description="fnmatch patterns skipped instead of converted; the row keeps its reason."
    )
    converter: Literal["auto", "zwcad", "builtin"] = Field(
        description="`auto` prefers ZWCAD then falls back; `zwcad` fails without it; "
        "`builtin` never uses it."
    )
    zwcad_timeout_s: float = Field(
        gt=0, description="Seconds one file may take before the ZWCAD process tree is killed."
    )
    zwcad_dxf_version: str = Field(
        min_length=1, description="DXF version ZWCAD's SaveAs writes, e.g. `2013`."
    )
    crosscheck_sample: int = Field(
        ge=0,
        description="Files per set converted with both converters and compared; 0 disables it.",
    )


class MatchSettings(_Section):
    """How a before frame is paired with an after frame."""

    fingerprint_tolerance: float = Field(
        gt=0, description="mm. Entity positions are rounded to this grid before fingerprinting."
    )
    title_jaccard_min: float = Field(
        ge=0, le=1, description="Minimum title similarity accepted when there is no drawing number."
    )


class MinorSettings(_Section):
    """Which differences are folded away as 사소한 변경."""

    move_tolerance: float = Field(
        ge=0, description="mm. A translation at most this long is minor (ledger: 0.01mm)."
    )
    fold: list[MinorFoldReason] = Field(
        description="Property-only differences folded away. A closed list, not free text."
    )


class ClusterSettings(_Section):
    """How nearby changes are grouped into one cloud mark."""

    grow_ratio: float = Field(
        gt=0, description="Fraction of the frame's long side used as the grouping distance."
    )
    grow_min: float = Field(
        gt=0, description="mm at 1:100. Floor for the distance `grow_ratio` computes."
    )


class CloudSettings(_Section):
    """Cloud mark and number badge geometry, in mm at 1:100 (compare-dxf.md §5)."""

    layer_prefix: str = Field(
        min_length=1, description="Layer is this plus the run date: `REV-20260904`."
    )
    color: int = Field(ge=1, le=255, description="ACI colour of the revision layer. 1 is red.")
    margin: float = Field(
        ge=0, description="Gap between the cluster's box and the cloud rectangle."
    )
    arc: float = Field(
        gt=0, description="Chord length of one arc; each side is divided evenly by it."
    )
    arc_bulge: float = Field(
        gt=0,
        description="LWPOLYLINE bulge, tan(theta/4). 0.5 is roughly 106 degrees, convex outwards.",
    )
    badge_side: float = Field(gt=0, description="Side of the equilateral number triangle.")
    badge_text_height: float = Field(gt=0, description="Height of the number inside the triangle.")
    badge_anchor: Literal["top_right"] = Field(
        description="Where the triangle sits. R1 draws only the outer top-right corner."
    )


class RevTableSettings(_Section):
    """The revision table drawn on the markup DWG (compare-dxf.md §6)."""

    columns: list[str] = Field(
        min_length=1,
        description="Column headings, and the header row itself. No 담당 column (ledger).",
    )
    col_widths: list[float] = Field(
        min_length=1, description="mm at 1:100, one per column, same order as `columns`."
    )
    row_height: float = Field(gt=0, description="mm at 1:100, header row included.")
    text_height: float = Field(gt=0, description="mm at 1:100.")
    anchor: Literal["titleblock_left"] = Field(
        description="The table's top-right meets the title block's top-left, growing down."
    )

    @model_validator(mode="after")
    def _widths_match_columns(self) -> RevTableSettings:
        """A width per column, or the table is drawn with mismatched cells.

        Easy to get wrong by hand -- someone adds a 담당 column and forgets the
        width -- and the failure would only show up as a crooked table on a
        printed drawing, so it is caught at load instead.
        """
        if len(self.col_widths) != len(self.columns):
            raise ValueError(
                f"col_widths has {len(self.col_widths)} entries but columns has {len(self.columns)}"
            )
        return self


class OutputSettings(_Section):
    """Where the export writes and what it writes with."""

    dir_name: str = Field(
        min_length=1,
        description="Folder under the project: `<프로젝트>/<dir_name>/<run_date>[-n]/`.",
    )
    file_pattern: str = Field(
        min_length=1,
        description="Markup file stem; `{sheet_no}` and `{after_label}` are substituted.",
    )
    dwg_writer: Literal["auto", "zwcad", "acad-ts", "dxf-only"] = Field(
        description="`auto` tries ZWCAD, then acad-ts, then writes a DXF instead."
    )


class CompareConfig(_Section):
    """``<프로젝트>/.halo/compare.yaml``, merged over the packaged defaults."""

    schema_version: str = Field(description="Contract version of this file, `<major>.<minor>`.")
    ingest: IngestSettings
    match: MatchSettings
    minor: MinorSettings
    cluster: ClusterSettings
    cloud: CloudSettings
    revtable: RevTableSettings
    output: OutputSettings

    def revision_layer(self, run_date: str, *, suffix: int | None = None) -> str:
        """`REV-<YYYYMMDD>`, or `REV-<YYYYMMDD>-<n>` for a later export the same day.

        The compare DXF never carries the suffix; only the export does
        (``docs/contracts/compare-dxf.md`` §2). ``run_date`` is `YYYY-MM-DD`.
        """
        compact = run_date.replace("-", "")
        base = f"{self.cloud.layer_prefix}{compact}"
        return base if suffix is None or suffix <= 1 else f"{base}-{suffix}"


class TitleblockSettings(_Section):
    """Which block counts as a title block, and which ATTRIB tag holds what."""

    min_attribs: int = Field(
        ge=1, description="A candidate block needs at least this many ATTRIBs."
    )
    number_tags: list[str] = Field(description="Drawing-number tag candidates, best first.")
    title_tags: list[str] = Field(description="Drawing-name tag candidates, best first.")
    scale_tags: list[str] = Field(
        description="Scale tag candidates; the denominator is parsed out."
    )
    date_tags: list[str] = Field(
        description="Date tag candidates. Read for display only -- never used as the run date."
    )
    fallback_most_common_block: bool = Field(
        description="When no tag matches, take the most repeated block with enough ATTRIBs."
    )
    block_name_patterns: list[str] = Field(
        description="When non-empty, only blocks whose name matches one of these are candidates."
    )


class FrameSettings(_Section):
    """How the frame outline is found and which entities belong to it."""

    boundary: Literal["smallest_enclosing_rect"] = Field(
        description="Smallest closed rectangular LWPOLYLINE that contains the title block."
    )
    fallback: Literal["modal_size_titleblock_bottom_right"] = Field(
        description="No outline found: the file's most common frame size, title block "
        "at its bottom-right."
    )
    assign: Literal["bbox_center"] = Field(
        description="An entity belongs to the frame its bounding-box centre falls in."
    )


class NormalizeSettings(_Section):
    """Text folding applied before two sheet numbers or titles are compared."""

    strip_spaces: bool = Field(description="Remove every space.")
    fullwidth_to_ascii: bool = Field(description="Fold full-width characters to ASCII.")
    upper: bool = Field(description="Upper-case letters.")
    unify_hyphen: bool = Field(description="Rewrite hyphen variants to the ASCII hyphen.")


class FramesConfig(_Section):
    """``<프로젝트>/.halo/frames.yaml``, merged over the packaged defaults."""

    schema_version: str = Field(description="Contract version of this file, `<major>.<minor>`.")
    titleblock: TitleblockSettings
    frame: FrameSettings
    normalize: NormalizeSettings


class HasBundleLayout(Protocol):
    """Anything that knows its bundle layout -- in practice ``BundleHandle``."""

    @property
    def layout(self) -> BundleLayout: ...


BundleLike = BundleLayout | HasBundleLayout | Path | str
"""What the loaders accept: an open bundle, its layout, or the bundle root path."""


def _layout_of(bundle: BundleLike) -> BundleLayout:
    if isinstance(bundle, BundleLayout):
        return bundle
    if isinstance(bundle, str | Path):
        return BundleLayout(Path(bundle))
    layout = getattr(bundle, "layout", None)
    if not isinstance(layout, BundleLayout):
        raise TypeError(
            f"expected a BundleHandle, a BundleLayout or a bundle path, got {type(bundle).__name__}"
        )
    return layout


def _read_yaml(path: Path) -> dict[str, Any]:
    """Parse one settings file into a mapping. An empty file is an empty mapping."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise CompareConfigError(path, [f"cannot be read: {error}"]) from error
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise CompareConfigError(path, [f"YAML syntax: {error}"]) from error
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise CompareConfigError(
            path, [f"top level must be a mapping, not {type(loaded).__name__}"]
        )
    return loaded


def _merge(defaults: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Overlay ``overrides`` onto ``defaults``, key by key.

    Nested mappings merge; anything else replaces. A list replaces wholesale
    rather than concatenating -- ``ignore_patterns`` and ``fold`` are complete
    statements of what to skip and what to fold, and appending to them behind
    the user's back would make a shortened list impossible to express.
    """
    merged = dict(defaults)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged


def _copy_default_if_missing(default_path: Path, target_path: Path) -> None:
    """Put the packaged file in the bundle, comments and all, if it is not there yet.

    ``copyfile`` rather than a dump of the parsed values: the comments are the
    documentation the person editing the file will read.
    """
    if target_path.exists():
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(default_path, target_path)


def _load[ConfigT: BaseModel](
    bundle: BundleLike,
    *,
    default_path: Path,
    target: str,
    model: type[ConfigT],
) -> ConfigT:
    layout = _layout_of(bundle)
    target_path = getattr(layout, target)
    _copy_default_if_missing(default_path, target_path)

    defaults = _read_yaml(default_path)
    project = _read_yaml(target_path)
    merged = _merge(defaults, project)

    try:
        return model.model_validate(merged)
    except ValidationError as error:
        reasons = [
            f"{'.'.join(str(part) for part in item['loc']) or '<root>'}: {item['msg']}"
            for item in error.errors()
        ]
        raise CompareConfigError(target_path, reasons) from error


def load_compare_config(bundle: BundleLike) -> CompareConfig:
    """Read ``<bundle>/compare.yaml``, creating it from the defaults on first use."""
    return _load(
        bundle, default_path=DEFAULT_COMPARE_YAML, target="compare_yaml", model=CompareConfig
    )


def load_frames_config(bundle: BundleLike) -> FramesConfig:
    """Read ``<bundle>/frames.yaml``, creating it from the defaults on first use."""
    return _load(bundle, default_path=DEFAULT_FRAMES_YAML, target="frames_yaml", model=FramesConfig)


def scale_factor(scale_denominator: int | None) -> float:
    """Multiplier from the 1:100 reference sizes to this sheet's model units.

    ``1:50`` draws everything half as large in model space, so the 100mm arc has
    to be 50mm; ``1:200`` doubles it. A sheet whose scale could not be read is
    treated as 1:100 rather than guessed, because a wrong factor is worse than a
    cloud mark that is the wrong size on one sheet
    (``docs/contracts/compare-dxf.md`` §5).
    """
    if scale_denominator is None or scale_denominator <= 0:
        return 1.0
    return scale_denominator / REFERENCE_SCALE_DENOMINATOR


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "DEFAULTS_DIR",
    "DEFAULT_COMPARE_YAML",
    "DEFAULT_FRAMES_YAML",
    "REFERENCE_SCALE_DENOMINATOR",
    "BundleLike",
    "ClusterSettings",
    "CloudSettings",
    "CompareConfig",
    "CompareConfigError",
    "FrameSettings",
    "FramesConfig",
    "IngestSettings",
    "MatchSettings",
    "MinorFoldReason",
    "MinorSettings",
    "NormalizeSettings",
    "OutputSettings",
    "RevTableSettings",
    "TitleblockSettings",
    "load_compare_config",
    "load_frames_config",
    "scale_factor",
]
