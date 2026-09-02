"""File ingest pipeline: DXF loading, encoding correction, XREF embedding,
working-DXF canonicalisation and layer statistics (ADR-0002).

Submodules:

``dxf_loader``
    ``ezdxf.readfile`` with an ``ezdxf.recover`` fallback and header/audit
    extraction.
``encoding``
    Mojibake scoring/retry for pre-R2007 codepages, and ``\\M+`` / ``\\U+``
    escape decoding.
``xref``
    XREF path resolution and embedding (``ezdxf.xref``), with a bound
    handle map.
``entity_index``
    Flat per-top-level-entity record generator (SQLite storage is W6-01).
``stats``
    Independent ``LayerStatsDocument`` computation (``docs/contracts/stats-definition.md``).
``working_dxf``
    Combines the above into the working-DXF canonical form (R2018 UTF-8).
"""

from __future__ import annotations
