"""``GET /api/v1/compare/zwcad/status`` (brief R1-02, docs/contracts/r1.md §6.1/§7)."""

from __future__ import annotations

from fastapi import APIRouter

from halo_engine.compare.zwcad import ZwcadStatus, detect

router = APIRouter()


@router.get("/zwcad/status", response_model=ZwcadStatus)
async def zwcad_status() -> ZwcadStatus:
    """Whether this process can convert via the hidden ZWCAD COM bridge right now.

    Registry + comtypes-import check only (``compare.zwcad.detect``) -- never
    launches a COM instance, so this is safe to poll from the desktop UI.
    """
    return detect()
