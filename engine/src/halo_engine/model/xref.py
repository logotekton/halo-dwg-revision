"""XREF resolution resource models (brief W3-06: ``api/routers/xrefs.py``).

Strict mypy is configured for this package (``engine/pyproject.toml``).
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class XrefLinkStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class XrefLinkSummary(BaseModel):
    """One row of ``GET /files/{id}/xrefs`` -- one XREF block definition and
    whether the last (re-)import could embed it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    block_name: str
    declared_path: str
    resolved_path: str | None = None
    status: XrefLinkStatus


class XrefResolveRequest(BaseModel):
    """``POST /files/{id}/xrefs/{name}/resolve`` body: the user manually
    matched one unresolved XREF block to a file on disk (brief Goal:
    "파일을 개별 매칭하면"). Its parent directory is added to the project's
    persisted search paths (the same mechanism a folder pick uses) and the
    host is re-imported."""

    model_config = ConfigDict(extra="forbid")

    resolved_path: str = Field(description="Absolute path to the file the user picked.")


class XrefResolveResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    file_id: str


class SearchPathsUpdateRequest(BaseModel):
    """``PUT /projects/{id}/search-paths`` body (brief Goal: "폴더를 지정하면
    ... 검색 경로에 저장되고 재임포트가 실행된다"). Replaces the project's
    whole search-path list -- the caller (UI) already holds the current
    list (from ``GET .../import-settings``) and appends to it, matching how
    ``PUT`` is used everywhere else in this API (``drawing_file`` full-row
    updates via ``repos.update_drawing_file``)."""

    model_config = ConfigDict(extra="forbid")

    search_paths: list[str] = Field(default_factory=list)
    #: File ids to re-import with the new search paths once saved. Empty
    #: just persists the setting (e.g. from the settings panel) without
    #: kicking off a job.
    reimport_file_ids: list[str] = Field(default_factory=list)


class SearchPathsUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    search_paths: list[str]
    #: One job per re-imported file (``api/jobs.py`` re-imports one file at
    #: a time so a search-path change to a single unresolved host does not
    #: re-run every other file in the same drawing set).
    job_ids: list[str] = Field(default_factory=list)


class ImportSettings(BaseModel):
    """``GET``/``PUT /projects/{id}/import-settings``: the project-wide XREF
    search paths and the ``import.ignore_patterns`` exclusion list (brief
    addendum 3, "설정 UI는 단순 텍스트 목록") in one place."""

    model_config = ConfigDict(extra="forbid")

    search_paths: list[str] = Field(default_factory=list)
    ignore_patterns: list[str] = Field(default_factory=list)


__all__ = [
    "ImportSettings",
    "SearchPathsUpdateRequest",
    "SearchPathsUpdateResponse",
    "XrefLinkStatus",
    "XrefLinkSummary",
    "XrefResolveRequest",
    "XrefResolveResponse",
]
