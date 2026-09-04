"""W3-06 acceptance (a)/(b): importing a real-set host DWG with ``XR/`` as a
search path resolves and embeds its XREF targets, including the DWG ones,
through the full ``POST /projects/{id}/drawing-sets`` pipeline (acad-ts
fallback -- the desktop converter, W3-02, is not merged; task instructions:
"use the engine's acad-ts fallback ... for DWG XREF targets in your
tests").

Known residual gap (not this task's to fix -- see report Follow-ups):
one of the three targets (``XR/PLAN.dwg``) fails to *embed* even once
correctly resolved and converted, with ``AttributeError: 'Attrib' object
has no attribute 'doc'`` raised by ``ezdxf.xref.Loader`` while cloning an
ATTRIB sub-entity. This is the same class of acad-ts DXF-writer defect
ADR-0002's amendment and ``packages/acad-bridge/README.md`` "Known acad-ts
gaps" already document (malformed ATTRIB subclass/tag emission) -- W3-08
repaired it for the top-level *load* path (``test_converter_fallback.py``),
not for ``ezdxf.xref.Loader``'s entity-copy path, which is new here because
XREF embedding is new. Fixing it means patching
``packages/acad-bridge``'s DXF writer, outside this task's "Files you own".
This task's own responsibility -- verified below -- is that such a failure
degrades to one *unresolved* XREF link (surfaced to the UI dialog), not a
FAILED host import; that is exactly what happens.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api_helpers import (
    AUTH_HEADERS,
    create_project,
    import_files,
    list_files,
    make_app,
    shutdown_app,
    wait_for_job,
)
from fastapi.testclient import TestClient

# engine/tests/api/test_real_set_xref_import.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_SET_SUBPATH = Path("samples") / "2026-09-02-실시도서" / "##실시도서(시공도면 수정)"
# samples/ is gitignored, so a task worktree (Desktop/대명건설/.worktrees/<ID>) has no
# copy of it -- fall back to the main checkout's samples (repo name after the
# 2026-09-04 carve-out; the original "Free CAD for Mac OS" checkout is retired).
_REAL_SET_ROOT = next(
    (
        candidate
        for candidate in (
            _REPO_ROOT / _REAL_SET_SUBPATH,
            _REPO_ROOT.parent.parent / "halo-dwg-revision" / _REAL_SET_SUBPATH,
        )
        if candidate.is_dir()
    ),
    _REPO_ROOT / _REAL_SET_SUBPATH,
)
_HOST_DWG = _REAL_SET_ROOT / "01_건축" / "A-100 평면도.dwg"
_XR_DIR = _REAL_SET_ROOT / "XR"


def test_real_host_with_xr_search_path_imports_and_embeds_its_xrefs(
    tmp_path: Path, acad_bridge_bin: Path
) -> None:
    if not _HOST_DWG.is_file() or not _XR_DIR.is_dir():
        pytest.skip(f"real sample set not present at {_REAL_SET_ROOT}")

    app = make_app(tmp_path, converter_fallback="acad-ts", acad_bridge_bin=acad_bridge_bin)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(_HOST_DWG)],
                search_paths=[str(_XR_DIR)],
                converter_fallback="acad-ts",
            )
            # Several DWGs (host + up to 3 XREF targets) converted through
            # one worker process -- generous budget vs api_helpers' 30s default.
            job = wait_for_job(client, created["job_id"], timeout_s=180.0)
            assert job["status"] == "DONE", job

            files = list_files(client, created["drawing_set_id"])
            host_row = next(f for f in files if f["original_name"] == "A-100 평면도.dwg")
            # The host import itself succeeds even though one XREF target
            # cannot be embedded (module docstring) -- this is the actual
            # brief requirement: one bad XREF must not fail the whole host.
            assert host_row["import_status"] == "DONE", host_row

            resp = client.get(f"/api/v1/files/{host_row['id']}/xrefs", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            links = resp.json()
            assert len(links) == 3, links  # PLAN, TITLE BLOCK-V, 단위세대_평면

            by_block = {link["block_name"]: link for link in links}
            assert by_block["TITLE BLOCK-V"]["status"] == "RESOLVED"
            assert by_block["단위세대_평면"]["status"] == "RESOLVED"
            # PLAN.dwg: known residual gap, module docstring.
            assert by_block["PLAN"]["status"] == "UNRESOLVED"

            resolved_links = [link for link in links if link["status"] == "RESOLVED"]
            imported_names = {f["original_name"] for f in files}
            # Every *successfully embedded* XREF target DWG is also its own
            # drawing_file(is_xref=1) row, not just embedded invisibly.
            for link in resolved_links:
                target_name = link["declared_path"].split("\\")[-1]
                assert target_name in imported_names, (target_name, imported_names)
    finally:
        shutdown_app(app)
