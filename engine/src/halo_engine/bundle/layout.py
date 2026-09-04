"""``<name>.halo/`` bundle path layout (``docs/PLAN.md`` §4, verbatim).

::

    <name>.halo/
      project.json
      project.sqlite
      originals/<sha256>.<ext>      # 0444, CLAUDE.md rule 1
      cache/dxf/<sha256>.working.dxf
      cache/mesh/<run>/<floor>.glb
      derivatives/
      sidecars/*.json
      exports/

R1 (``docs/contracts/r1.md`` §2) puts the bundle at ``<프로젝트>/.halo`` and adds
the revision-comparison paths to the same root::

    .halo/
      compare/<pair_id>/compare.dxf, clusters.json, markup.dxf
      compare.yaml, frames.yaml      # copied from the defaults on first use
      log/<compare_set_id>.log       # conversion log, crosscheck mismatches

Together with ``<프로젝트>/출력/<날짜>/`` these are the only paths anything is
allowed to write (CLAUDE.md rule 1); ``bundle.guard.assert_writable_path``
enforces it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

BUNDLE_SUFFIX = ".halo"

#: A ``sheet_pair`` id is a ULID, and it becomes a directory name. Anything else
#: is refused rather than joined onto the bundle root, so a value that reached
#: the engine from a request body can never walk out of it.
_PAIR_ID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")

#: Defaults for ambiguity (brief W3-03): no ``path`` given to ``POST /projects``.
DEFAULT_PROJECTS_ROOT = Path.home() / "Documents" / "Halo CAD"


def default_bundle_path(name: str) -> Path:
    """``~/Documents/Halo CAD/<name>.halo`` -- the brief's default bundle location."""
    return DEFAULT_PROJECTS_ROOT / f"{name}{BUNDLE_SUFFIX}"


@dataclass(frozen=True)
class BundleLayout:
    """Resolved paths for one bundle root. Construction never touches the filesystem."""

    root: Path

    @property
    def project_json(self) -> Path:
        return self.root / "project.json"

    @property
    def project_sqlite(self) -> Path:
        return self.root / "project.sqlite"

    @property
    def originals_dir(self) -> Path:
        return self.root / "originals"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def cache_dxf_dir(self) -> Path:
        return self.cache_dir / "dxf"

    @property
    def cache_mesh_dir(self) -> Path:
        return self.cache_dir / "mesh"

    @property
    def derivatives_dir(self) -> Path:
        return self.root / "derivatives"

    @property
    def sidecars_dir(self) -> Path:
        return self.root / "sidecars"

    @property
    def exports_dir(self) -> Path:
        return self.root / "exports"

    @property
    def compare_dir(self) -> Path:
        """``compare/`` -- one sub-directory per sheet pair (R1)."""
        return self.root / "compare"

    @property
    def log_dir(self) -> Path:
        """``log/`` -- one ``<compare_set_id>.log`` per comparison (R1)."""
        return self.root / "log"

    @property
    def compare_yaml(self) -> Path:
        """Project-level comparison settings. Copied from the defaults when missing."""
        return self.root / "compare.yaml"

    @property
    def frames_yaml(self) -> Path:
        """Project-level title-block recognition settings. Copied from the defaults when missing."""
        return self.root / "frames.yaml"

    def compare_pair_dir(self, pair_id: str) -> Path:
        """``compare/<pair_id>/`` -- where one pair's compare DXF and sidecar live.

        Raises ``ValueError`` for anything that is not a ULID: the value comes
        from a request path, and a directory name is not the place to trust it.
        """
        if not _PAIR_ID_RE.match(pair_id):
            raise ValueError(f"not a sheet_pair id: {pair_id!r}")
        return self.compare_dir / pair_id

    def ensure_dirs(self) -> None:
        for directory in (
            self.originals_dir,
            self.cache_dxf_dir,
            self.cache_mesh_dir,
            self.derivatives_dir,
            self.sidecars_dir,
            self.exports_dir,
            self.compare_dir,
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


__all__ = ["BUNDLE_SUFFIX", "DEFAULT_PROJECTS_ROOT", "BundleLayout", "default_bundle_path"]
