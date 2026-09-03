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
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BUNDLE_SUFFIX = ".halo"

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

    def ensure_dirs(self) -> None:
        for directory in (
            self.originals_dir,
            self.cache_dxf_dir,
            self.cache_mesh_dir,
            self.derivatives_dir,
            self.sidecars_dir,
            self.exports_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


__all__ = ["BUNDLE_SUFFIX", "DEFAULT_PROJECTS_ROOT", "BundleLayout", "default_bundle_path"]
