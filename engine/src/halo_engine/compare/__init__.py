"""Revision comparison: 도곽 추출 → 짝짓기 → 비교 → 마크업 (R1).

The package the whole R1 pipeline lives in (``docs/contracts/r1.md`` §6). Every
module below is a pure computation over an ezdxf document plus the settings in
:mod:`halo_engine.compare.config`; the API routers and the job runner only
orchestrate them, and the viewer draws what they produce.

============================  ========  =========================================
module                        task      what it owns
============================  ========  =========================================
``config``                    R1-01     ``compare.yaml`` / ``frames.yaml``
``zwcad``                     R1-02     the background ZWCAD COM converter
``ingest_set``                R1-03     one set folder -> working DXFs
``frames``, ``match``         R1-04     title blocks and sheet pairing
``diff``, ``cluster``,        R1-06     entity diff, cloud marks, compare DXF
``compare_dxf``, ``labels``
``markup``, ``export``        R1-09     markup DWG, revision table, 출력/
============================  ========  =========================================

Only :mod:`~halo_engine.compare.config` is imported here. It is deliberately
light -- pyyaml and pydantic, no ezdxf -- so that reading a project's settings
never drags the DXF stack into a process that just wants to answer a request.
"""

from __future__ import annotations

from halo_engine.compare.config import (
    CompareConfig,
    CompareConfigError,
    FramesConfig,
    load_compare_config,
    load_frames_config,
    scale_factor,
)

__all__ = [
    "CompareConfig",
    "CompareConfigError",
    "FramesConfig",
    "load_compare_config",
    "load_frames_config",
    "scale_factor",
]
