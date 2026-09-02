"""Common return type for fixture builder functions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ezdxf.document import Drawing


@dataclass
class BuildResult:
    doc: Drawing
    #: human-readable notes about entities/features skipped for this DXF
    #: version (e.g. MLEADER on R2000); recorded verbatim into truth JSON.
    omitted: list[str] = field(default_factory=list)
    #: fixture-specific ground truth (member placements, table cells,
    #: level fields, gaps, ...) written verbatim under truth["extra"].
    extra: dict[str, Any] = field(default_factory=dict)
