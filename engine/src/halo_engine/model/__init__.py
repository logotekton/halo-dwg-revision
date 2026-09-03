"""Part/space/surface model (member DB, solids, prisms, surface attributes).

Strict mypy is configured for this package (see ``engine/pyproject.toml``), so
every module here is type-checked from day one.

``crosscheck`` (W2-04) is the persisted parser-crosscheck report, stored on
``drawing_file.parser_crosscheck``; the comparison that produces it lives in
:mod:`halo_engine.validate.crosscheck`. ``project``/``drawing`` (W3-03) are
the project-bundle and drawing-set/file/job API resource models.
"""

from halo_engine.model.crosscheck import (
    CrosscheckReport,
    Difference,
    DiffField,
    LayerResult,
    ProducerInfo,
    Severity,
)
from halo_engine.model.drawing import (
    ConvertedAck,
    ConvertedRequest,
    ConverterName,
    DrawingFileSummary,
    DrawingFormat,
    DrawingSetCreateRequest,
    DrawingSetCreateResponse,
    ImportStatus,
    JobStatus,
    JobSummary,
)
from halo_engine.model.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectOpenRequest,
    ProjectSummary,
    RecentProjectEntry,
)
from halo_engine.model.xref import (
    ImportSettings,
    SearchPathsUpdateRequest,
    SearchPathsUpdateResponse,
    XrefLinkStatus,
    XrefLinkSummary,
    XrefResolveRequest,
    XrefResolveResponse,
)

__all__ = [
    "ConverterName",
    "ConvertedAck",
    "ConvertedRequest",
    "CrosscheckReport",
    "DiffField",
    "Difference",
    "DrawingFileSummary",
    "DrawingFormat",
    "DrawingSetCreateRequest",
    "DrawingSetCreateResponse",
    "ImportSettings",
    "ImportStatus",
    "JobStatus",
    "JobSummary",
    "LayerResult",
    "ProducerInfo",
    "ProjectCreateRequest",
    "ProjectCreateResponse",
    "ProjectOpenRequest",
    "ProjectSummary",
    "RecentProjectEntry",
    "SearchPathsUpdateRequest",
    "SearchPathsUpdateResponse",
    "Severity",
    "XrefLinkStatus",
    "XrefLinkSummary",
    "XrefResolveRequest",
    "XrefResolveResponse",
]
