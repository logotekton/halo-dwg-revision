"""JSON Schema validation for the Python side.

The pydantic models describe the shape of a document. They cannot express the
conditional rules the contract is built on, above all ADR-0003: equality is
only legal between two readings of the same structural basis, and any check
touching the ceiling height ``CH`` must be an inequality. Those rules live in
the schema, so the Python side validates against the schema exactly as the
viewer does with ajv, and both sides reject the same documents.

Needs the ``validation`` extra::

    pip install "halo-schema[validation]"

This module is hand written; it is not regenerated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from . import CONSISTENCY_CHECK_POINTER, SCHEMA_IDS, all_schemas


@lru_cache(maxsize=1)
def registry() -> Registry:
    """Every schema registered under its own ``$id``.

    The absolute ``$ref`` URIs resolve inside this registry, so validation never
    touches the network.
    """
    resources = [
        (SCHEMA_IDS[key], Resource.from_contents(schema, default_specification=DRAFT202012))
        for key, schema in all_schemas().items()
    ]
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def validator_for(uri: str) -> Draft202012Validator:
    """Compiled validator for a schema ``$id``, optionally with a JSON pointer."""
    return Draft202012Validator({"$ref": uri}, registry=registry())


def validator(key: str) -> Draft202012Validator:
    """Compiled validator for one of the keys of :data:`halo_schema.SCHEMA_IDS`."""
    return validator_for(SCHEMA_IDS[key])


def consistency_check_validator() -> Draft202012Validator:
    """Validator for a single consistency check definition."""
    return validator_for(CONSISTENCY_CHECK_POINTER)


def is_valid(key: str, document: Any) -> bool:
    """True when ``document`` satisfies the named schema."""
    return validator(key).is_valid(document)


def failures(key: str, document: Any) -> list[str]:
    """Human readable failures, in document order. Empty when the document is valid."""
    return [
        f"{'/' + '/'.join(str(part) for part in error.absolute_path) or '/'}: {error.message}"
        for error in sorted(validator(key).iter_errors(document), key=lambda e: list(e.absolute_path))
    ]


class SchemaValidationError(ValueError):
    """Raised by :func:`assert_valid`."""

    def __init__(self, label: str, reasons: list[str], schema_id: str) -> None:
        super().__init__(f"{label} failed schema validation: {'; '.join(reasons)}")
        self.reasons = reasons
        self.schema_id = schema_id


def assert_valid(key: str, document: Any, label: str = "document") -> Any:
    """Return ``document`` or raise :class:`SchemaValidationError`."""
    reasons = failures(key, document)
    if reasons:
        raise SchemaValidationError(label, reasons, SCHEMA_IDS[key])
    return document


__all__ = [
    "SchemaValidationError",
    "assert_valid",
    "consistency_check_validator",
    "failures",
    "is_valid",
    "registry",
    "validator",
    "validator_for",
]
