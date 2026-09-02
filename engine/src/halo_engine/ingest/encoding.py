"""Encoding correction for pre-R2007 DXF files (brief W2-03).

DXF R2007 (``AC1021``) and newer always store text as UTF-8, so there is
nothing to correct there (``codepage_effective`` is simply ``"UTF-8"``).
Older files declare a Windows codepage in ``$DWGCODEPAGE`` (e.g.
``ANSI_949`` for Korean cp949); ezdxf decodes text using that declared
codepage automatically. The problem this module solves is a *wrong*
declaration -- files authored on a Korean system whose ``$DWGCODEPAGE``
was left at the ANSI_1252 default (or was otherwise mis-set) decode as
mojibake. :func:`resolve_codepage` re-reads the file with ``cp949`` and
keeps whichever decode scores better.

Score (docs/contracts/stats-definition.md, brief Constraints): the ratio of
Korean syllable characters (``U+AC00``-``U+D7A3``) minus the ratio of
mojibake indicator characters (Latin-1 Supplement ``U+00C0``-``U+00FF``,
plus the literal replacement character ``U+FFFD``), both over the total
character count of every TEXT/MTEXT/ATTRIB string in the document. A
higher score is a more plausible decode; ties keep the originally declared
codepage.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

import ezdxf
from ezdxf.document import Drawing

from halo_engine.ingest.dxf_loader import LoadResult, load_dxf

#: DXF versions below this store text per $DWGCODEPAGE; at or above, UTF-8.
R2007_ACADVER = "AC1021"

#: Codepage retried when the declared one looks wrong for a Korean drawing.
RETRY_CODEC = "cp949"

_KOREAN_SYLLABLES = (0xAC00, 0xD7A3)
_MOJIBAKE_RANGE = (0x00C0, 0x00FF)
_REPLACEMENT_CHAR = "�"


@dataclass(frozen=True)
class CodepageResolution:
    """Result of :func:`resolve_codepage`."""

    codepage_declared: str | None
    codepage_effective: str
    retried: bool
    declared_score: float | None
    retry_score: float | None


def _document_text_sample(doc: Drawing) -> str:
    """Every TEXT/MTEXT/ATTRIB string in the document, space-joined.

    Deliberately independent of :mod:`halo_engine.ingest.stats` (no shared
    import -- this only needs *a* representative text sample, not the exact
    bucketed aggregate).
    """
    parts: list[str] = []
    for layout in doc.layouts:
        for entity in layout:
            etype = entity.dxftype()
            if etype == "TEXT":
                parts.append(entity.dxf.text)
            elif etype == "MTEXT":
                parts.append(entity.text)
            elif etype == "INSERT":
                for attrib in entity.attribs:
                    parts.append(attrib.dxf.text)
    return "\n".join(parts)


def mojibake_score(text: str) -> float:
    """Korean-syllable ratio minus mojibake-indicator ratio, in ``[-1, 1]``.

    Returns ``0.0`` for an empty sample (no text to judge either way).
    """
    if not text:
        return 0.0
    korean = 0
    suspect = 0
    for ch in text:
        code = ord(ch)
        if _KOREAN_SYLLABLES[0] <= code <= _KOREAN_SYLLABLES[1]:
            korean += 1
        elif _MOJIBAKE_RANGE[0] <= code <= _MOJIBAKE_RANGE[1] or ch == _REPLACEMENT_CHAR:
            suspect += 1
    total = len(text)
    return (korean / total) - (suspect / total)


def resolve_codepage(path: str, load_result: LoadResult | None = None) -> CodepageResolution:
    """Decide the effective codepage for the DXF at ``path``.

    ``load_result`` lets a caller that already ran :func:`~halo_engine.ingest.dxf_loader.load_dxf`
    reuse that read instead of re-parsing the file; a fresh load is done
    otherwise.
    """
    result = load_result if load_result is not None else load_dxf(path)
    doc = result.doc

    if doc.dxfversion >= R2007_ACADVER:
        return CodepageResolution(
            codepage_declared=None,
            codepage_effective="UTF-8",
            retried=False,
            declared_score=None,
            retry_score=None,
        )

    declared_score = mojibake_score(_document_text_sample(doc))
    declared_codec = doc.encoding

    if not _document_text_sample(doc):
        # Nothing to score against -- keep the declared codepage rather than
        # guessing from an empty sample.
        return CodepageResolution(
            codepage_declared=result.dwgcodepage,
            codepage_effective=declared_codec,
            retried=False,
            declared_score=declared_score,
            retry_score=None,
        )

    if declared_codec == RETRY_CODEC:
        # Already what the retry would try; no point re-reading.
        return CodepageResolution(
            codepage_declared=result.dwgcodepage,
            codepage_effective=declared_codec,
            retried=False,
            declared_score=declared_score,
            retry_score=None,
        )

    try:
        retry_doc = ezdxf.readfile(path, encoding=RETRY_CODEC)
    except (ezdxf.DXFError, OSError, UnicodeDecodeError, LookupError):
        return CodepageResolution(
            codepage_declared=result.dwgcodepage,
            codepage_effective=declared_codec,
            retried=False,
            declared_score=declared_score,
            retry_score=None,
        )

    retry_score = mojibake_score(_document_text_sample(retry_doc))
    if retry_score > declared_score:
        return CodepageResolution(
            codepage_declared=result.dwgcodepage,
            codepage_effective=RETRY_CODEC,
            retried=True,
            declared_score=declared_score,
            retry_score=retry_score,
        )
    return CodepageResolution(
        codepage_declared=result.dwgcodepage,
        codepage_effective=declared_codec,
        retried=True,
        declared_score=declared_score,
        retry_score=retry_score,
    )


def load_with_corrected_encoding(path: str) -> tuple[LoadResult, CodepageResolution]:
    """:func:`~halo_engine.ingest.dxf_loader.load_dxf`, then re-load with the
    retry codec if :func:`resolve_codepage` decides it reads better.

    Returns the :class:`~halo_engine.ingest.dxf_loader.LoadResult` whose
    ``doc`` is actually decoded with ``codepage_effective`` -- the initial
    read when the declared codepage won, a second read with ``cp949`` when
    the retry won.
    """
    initial = load_dxf(path)
    resolution = resolve_codepage(path, initial)
    if resolution.retried and resolution.codepage_effective == RETRY_CODEC:
        corrected = load_dxf(path, encoding=RETRY_CODEC)
        return corrected, resolution
    return initial, resolution


def decode_escapes(text: str) -> str:
    """Decode DXF ``\\M+cXXXX`` (MIF) and ``\\U+XXXX`` unicode escapes.

    Thin wrapper over ezdxf's own (undocumented-in-README but public)
    ``ezdxf.lldxf.encoding`` helpers, applied MIF-first since the two escape
    patterns do not overlap. NFC-normalises the result, matching every other
    text field in the contract (docs/contracts/stats-definition.md).
    """
    from ezdxf.lldxf.encoding import decode_dxf_unicode, decode_mif_to_unicode

    decoded = decode_mif_to_unicode(text)
    decoded = decode_dxf_unicode(decoded)
    return unicodedata.normalize("NFC", decoded)


__all__ = [
    "R2007_ACADVER",
    "RETRY_CODEC",
    "CodepageResolution",
    "decode_escapes",
    "load_with_corrected_encoding",
    "mojibake_score",
    "resolve_codepage",
]
