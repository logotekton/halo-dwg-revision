"""ULID primary keys (``docs/PLAN.md`` §4: "id ULID").

A tiny self-contained encoder rather than a new dependency (``CLAUDE.md``
rule 10 -- new third-party dependencies need an ADR): 48-bit millisecond
timestamp + 80-bit randomness, Crockford base32, 26 characters, lexically
sortable by creation time. Not required to be strictly monotonic within the
same millisecond -- nothing in this codebase relies on that.
"""

from __future__ import annotations

import os
import time

#: Crockford's base32 alphabet (excludes I, L, O, U to avoid transcription errors).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_CHARS = 26
_TIME_BITS = 48
_RANDOM_BYTES = 10  # 80 bits


def new_ulid(*, _now_ms: int | None = None, _random_bytes: bytes | None = None) -> str:
    """A fresh ULID. ``_now_ms``/``_random_bytes`` are test-only overrides."""
    timestamp_ms = _now_ms if _now_ms is not None else int(time.time() * 1000)
    randomness = _random_bytes if _random_bytes is not None else os.urandom(_RANDOM_BYTES)
    if len(randomness) != _RANDOM_BYTES:
        raise ValueError(f"randomness must be {_RANDOM_BYTES} bytes, got {len(randomness)}")

    value = (timestamp_ms & ((1 << _TIME_BITS) - 1)) << (_RANDOM_BYTES * 8)
    value |= int.from_bytes(randomness, "big")

    chars = []
    for i in range(_ULID_CHARS):
        shift = 5 * (_ULID_CHARS - 1 - i)
        chars.append(_ALPHABET[(value >> shift) & 0x1F])
    return "".join(chars)


__all__ = ["new_ulid"]
