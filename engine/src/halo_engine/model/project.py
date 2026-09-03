"""Project resource models (``docs/contracts/wave-3.md``: ``POST /projects``,
``POST /projects/open``, ``GET /projects/recent``, ``GET /projects/{id}``).

Exactly one bundle is open in the engine's workspace at a time (brief W3-03
Decisions). Strict mypy applies to this package (``engine/pyproject.toml``).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    """``POST /projects`` body."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Project display name.")
    path: str | None = Field(
        default=None,
        description=(
            "Absolute path for the new `<name>.halo` bundle. Omit for the "
            "default location, `~/Documents/Halo CAD/<name>.halo` "
            "(brief W3-03, Defaults for ambiguity)."
        ),
    )


class ProjectOpenRequest(BaseModel):
    """``POST /projects/open`` body."""

    model_config = ConfigDict(extra="forbid")

    bundle_path: str = Field(description="Absolute path to an existing `<name>.halo` bundle.")


class ProjectCreateResponse(BaseModel):
    """``POST /projects`` / ``POST /projects/open`` response: ``{id, bundle_path}``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    bundle_path: str


class ProjectSummary(BaseModel):
    """``GET /projects/{id}`` response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    bundle_path: str
    created_at: datetime
    updated_at: datetime


class RecentProjectEntry(BaseModel):
    """One row of ``GET /projects/recent``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    bundle_path: str
    last_opened_at: datetime


__all__ = [
    "ProjectCreateRequest",
    "ProjectCreateResponse",
    "ProjectOpenRequest",
    "ProjectSummary",
    "RecentProjectEntry",
]
