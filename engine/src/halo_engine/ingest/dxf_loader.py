"""DXF loading with a recovery fallback (brief W2-03, ADR-0002).

``ezdxf.readfile`` is tried first; if it raises because the file is
structurally broken, ``ezdxf.recover.readfile`` (a much more tolerant,
tag-level reader) is used instead. Either way the result carries the
document's :class:`ezdxf.audit.Auditor` errors, so callers can see how
trustworthy the read was without re-auditing themselves.

Unsupported or foreign entity types (including ``ACAD_PROXY_ENTITY`` and
anything ezdxf has no dedicated wrapper for) are preserved by ezdxf as
``DXFTagStorage`` and round-trip through ``Drawing.saveas`` unchanged; this
loader does not need to do anything special for that (verified in
``tests/ingest/test_dxf_loader.py::test_proxy_entity_is_preserved``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ezdxf
import ezdxf.recover
from ezdxf.audit import Auditor, ErrorEntry
from ezdxf.document import Drawing

#: DXF versions older than AC1014 (R14) are out of scope (docs/PLAN.md 5);
#: the sidecar surfaces this as a normal audit-style issue rather than a
#: crash so the caller can report it to the user.
MIN_SUPPORTED_ACADVER = "AC1014"


@dataclass(frozen=True)
class AuditIssue:
    """One :class:`ezdxf.audit.ErrorEntry`, serialised for JSON output."""

    code: int
    message: str
    handle: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "handle": self.handle}


@dataclass
class LoadResult:
    """Everything :func:`load_dxf` learns about one DXF file."""

    doc: Drawing
    recovered: bool
    audit_errors: list[AuditIssue]
    dwgcodepage: str | None
    acadver: str
    insunits: int
    fingerprintguid: str | None

    @property
    def audit_error_count(self) -> int:
        return len(self.audit_errors)


def _issue_from_entry(entry: ErrorEntry) -> AuditIssue:
    handle: str | None = None
    entity = entry.entity
    if entity is not None:
        try:
            handle = entity.dxf.handle
        except Exception:  # pragma: no cover - defensive, ezdxf entities always have dxf
            handle = None
    return AuditIssue(code=entry.code, message=entry.message, handle=handle)


def _header_fields(doc: Drawing) -> tuple[str | None, str, int, str | None]:
    header = doc.header
    dwgcodepage = header.get("$DWGCODEPAGE", None)
    acadver = str(header.get("$ACADVER", doc.dxfversion))
    try:
        insunits = int(header.get("$INSUNITS", 0))
    except (TypeError, ValueError):
        insunits = 0
    fingerprintguid = header.get("$FINGERPRINTGUID", None)
    return dwgcodepage, acadver, insunits, fingerprintguid


def load_dxf(path: str | Path, *, encoding: str | None = None) -> LoadResult:
    """Load a DXF file, falling back to :mod:`ezdxf.recover` on structural errors.

    Args:
        path: filesystem path of the DXF file.
        encoding: force a specific codec instead of the codepage ezdxf
            detects from ``$DWGCODEPAGE`` (used by :mod:`halo_engine.ingest.encoding`
            for the mojibake retry).

    The document is always audited (``Drawing.audit()`` on the happy path,
    the :class:`~ezdxf.audit.Auditor` that :func:`ezdxf.recover.readfile`
    already returns on the fallback path), so ``audit_errors`` reflects the
    same checks either way.
    """
    path = Path(path)
    recovered = False
    auditor: Auditor
    try:
        doc = (
            ezdxf.readfile(str(path), encoding=encoding) if encoding else ezdxf.readfile(str(path))
        )
        auditor = doc.audit()
    except (ezdxf.DXFError, OSError, UnicodeDecodeError):
        doc, auditor = ezdxf.recover.readfile(str(path))
        recovered = True

    audit_errors = [_issue_from_entry(e) for e in auditor.errors]
    dwgcodepage, acadver, insunits, fingerprintguid = _header_fields(doc)

    return LoadResult(
        doc=doc,
        recovered=recovered,
        audit_errors=audit_errors,
        dwgcodepage=dwgcodepage,
        acadver=acadver,
        insunits=insunits,
        fingerprintguid=fingerprintguid,
    )


__all__ = ["MIN_SUPPORTED_ACADVER", "AuditIssue", "LoadResult", "load_dxf"]
