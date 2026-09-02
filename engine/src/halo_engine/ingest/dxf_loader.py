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

Duplicate-handle diagnostics (brief W3-08, G0 follow-up 2): a malformed
producer can write two entities with the same DXF handle (observed on real
acad-ts-written DXF, see ``packages/acad-bridge/README.md`` "Known acad-ts
gaps" and ``halo_engine.ingest.stats``'s module docstring for the crash this
causes further down the pipeline). ezdxf logs this as a plain
``logger.warning`` during ``load_and_bind_dxf_content`` -- it never reaches
:class:`~ezdxf.audit.Auditor` (``auditor.errors``/``.fixes`` stay empty for
it) and would otherwise be silent noise on the engine's own log stream. This
loader captures it as a ``LoadResult.diagnostics`` entry instead, so a caller
gets the *cause* (duplicate handle at load time) alongside the *effect*
(``halo_engine.ingest.stats``'s ``dead-attrib`` diagnostic, once one of the
two entities has been fixed up -- destroyed -- by ``Drawing.audit()``).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
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

#: Diagnostic ``code`` for a duplicate DXF handle caught while loading (see module docstring).
DIAG_DUPLICATE_HANDLE = "duplicate-handle"

_DUPLICATE_HANDLE_RE = re.compile(r"non-unique entity handle #([0-9A-Fa-f]+)")


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
    #: ``{code, message, handle?}`` entries for load-time issues that are not
    #: :class:`~ezdxf.audit.Auditor` errors (module docstring: duplicate
    #: handles). Never raised as an exception; empty on a clean file.
    diagnostics: list[dict[str, Any]] = field(default_factory=list)

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


class _DuplicateHandleCapture(logging.Handler):
    """Context manager that, while attached, turns ezdxf's
    ``logger.warning("Found non-unique entity handle #...")``
    (``lldxf/loader.py``, fired while binding entities to the document -- see
    module docstring) into ``{code, message, handle}`` diagnostics on
    :attr:`diagnostics`, ignoring every other ``ezdxf`` logger record.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.diagnostics: list[dict[str, Any]] = []
        self._logger = logging.getLogger("ezdxf")

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        match = _DUPLICATE_HANDLE_RE.search(message)
        if match is None:
            return
        entry: dict[str, Any] = {
            "code": DIAG_DUPLICATE_HANDLE,
            "message": message,
            "handle": match.group(1),
        }
        self.diagnostics.append(entry)

    def __enter__(self) -> _DuplicateHandleCapture:
        self._logger.addHandler(self)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._logger.removeHandler(self)


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
        with _DuplicateHandleCapture() as capture:
            doc = (
                ezdxf.readfile(str(path), encoding=encoding)
                if encoding
                else ezdxf.readfile(str(path))
            )
            auditor = doc.audit()
    except (ezdxf.DXFError, OSError, UnicodeDecodeError):
        with _DuplicateHandleCapture() as capture:
            doc, auditor = ezdxf.recover.readfile(str(path))
        recovered = True
    diagnostics = capture.diagnostics

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
        diagnostics=diagnostics,
    )


__all__ = [
    "DIAG_DUPLICATE_HANDLE",
    "MIN_SUPPORTED_ACADVER",
    "AuditIssue",
    "LoadResult",
    "load_dxf",
]
