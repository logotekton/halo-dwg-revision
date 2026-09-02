"""Validation and cross-checking of ingested drawings.

W2-04 ships the parser crosscheck (ADR-0002 decision 6): two
``LayerStatsDocument``s from different parsers, compared bucket by bucket into
a :class:`~halo_engine.model.crosscheck.CrosscheckReport`.

Entry points: ``halo-engine crosscheck`` (:mod:`halo_engine.cli`),
``POST /api/v1/files/crosscheck``
(:mod:`halo_engine.api.routers.crosscheck`), and
:func:`halo_engine.validate.crosscheck.compare` in-process.
"""

from halo_engine.validate.crosscheck import (
    DEFAULT_WHITELIST,
    WhitelistEntry,
    WhitelistError,
    compare,
    load_whitelist,
    render_markdown,
)

__all__ = [
    "DEFAULT_WHITELIST",
    "WhitelistEntry",
    "WhitelistError",
    "compare",
    "load_whitelist",
    "render_markdown",
]
