"""Part/space/surface model (member DB, solids, prisms, surface attributes).

Strict mypy is configured for this package (see ``engine/pyproject.toml``), so
every module here is type-checked from day one.

``crosscheck`` (W2-04) is the first inhabitant: the persisted parser-crosscheck
report, stored on ``drawing_file.parser_crosscheck``. The comparison that
produces it lives in :mod:`halo_engine.validate.crosscheck`.
"""

from halo_engine.model.crosscheck import (
    CrosscheckReport,
    Difference,
    DiffField,
    LayerResult,
    ProducerInfo,
    Severity,
)

__all__ = [
    "CrosscheckReport",
    "DiffField",
    "Difference",
    "LayerResult",
    "ProducerInfo",
    "Severity",
]
