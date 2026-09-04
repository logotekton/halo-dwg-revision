"""도곽 짝짓기: which 변경 전 sheet is which 변경 후 sheet (contract §6, brief R1-04).

Pairing is the step that decides what the comparison is even *about*. Get it
wrong and the diff is not "these three walls moved" but "this entire sheet was
replaced", which is both useless and slow. The rules are the contract's four
stages, tried in order, each one only on what the previous stage left over:

1. **number** -- the same normalised drawing number on both sides, unique on
   both sides. This is the answer for essentially every real sheet, and it is
   the only stage that scores 1.0.
2. **title** -- token Jaccard over the drawing name, at least
   ``compare.yaml`` ``match.title_jaccard_min``, and *mutually* best: the after
   sheet has to be this before sheet's single best candidate and vice versa. A
   tie on either side means the user has to decide, not the matcher.
3. **position** -- same file, same reading position in it, frame size within
   1%. This catches the sheet whose number and title were both retyped, and it
   is deliberately last and scored 0.5 because "third box from the left" is
   circumstantial evidence.
4. **the rest** -- before only is ``removed``, after only is ``added``, and
   anything that had several equally good candidates along the way is
   ``unpaired``: shown in the list, excluded from comparison, waiting for the
   user to pair it by hand on screen B (``POST .../pairs/manual``).

A pair's ``status`` here is a *pre-comparison* status. It is ``pending`` --
matched, not yet diffed -- except for the two cases that are already decided
before any geometry is read: the two files are byte-identical, so the sheet is
``same``, or they came out of different converters, so they must not be
compared at all (``converter_mismatch``; contract §3, and
``docs/spikes/real-dwg-measurement.md`` §3 on how differently two converters
render the same DWG).

Deterministic (CLAUDE.md rule 6): every stage iterates sorted keys, every tie
is broken by an explicit key, and scores are rounded to three decimals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from halo_engine.compare.config import (
    DEFAULT_FRAMES_YAML,
    CompareConfig,
    FramesConfig,
)
from halo_engine.compare.frames import KIND_UNRECOGNIZED, FrameRecord, normalize_key

#: ``sheet_pair.status`` (contract §3). ``changed``/``same`` after a comparison
#: are R1-06's to set; matching only ever writes these.
STATUS_PENDING = "pending"
STATUS_SAME = "same"
STATUS_ADDED = "added"
STATUS_REMOVED = "removed"
STATUS_UNPAIRED = "unpaired"
STATUS_UNRECOGNIZED = "unrecognized"
STATUS_CONVERTER_MISMATCH = "converter_mismatch"

#: ``sheet_pair.match_method`` (contract §3). ``manual`` is written by the
#: router when the user pairs two frames by hand, never by this module.
METHOD_NUMBER = "number"
METHOD_TITLE = "title"
METHOD_POSITION = "position"

#: Score of a stage-1 (number) and a stage-3 (position) match. Stage 2 scores
#: the similarity it measured.
SCORE_NUMBER = 1.0
SCORE_POSITION = 0.5

#: Fraction. Two frames match by position only if both their width and their
#: height agree to within this (brief: "도곽 크기 ±1%").
POSITION_SIZE_TOLERANCE = 0.01

#: Digits every number inside a sort key is padded to, so ``A-99`` sorts before
#: ``A-101`` in a plain SQL ``ORDER BY sort_key`` (``repos.list_pairs``).
SORT_KEY_DIGITS = 8

#: What a drawing name is split into before the two token sets are compared.
_TITLE_SPLIT_RE = re.compile(r"[\s\-_()\[\]{}<>,./|~]+")
_DIGITS_RE = re.compile(r"(\d+)")


@dataclass
class PairRecord:
    """One 도곽 짝 before it becomes a ``sheet_pair`` row.

    Frames are referenced by their index in the two lists handed to
    :func:`match_frames`, which is the order ``repos.replace_frames`` inserted
    them in -- so the caller can turn indices into row ids without the matcher
    having to know anything about the database.
    """

    before_index: int | None = None
    after_index: int | None = None
    status: str = STATUS_PENDING
    match_method: str | None = None
    score: float | None = None
    sort_key: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_row(self, before_ids: list[str], after_ids: list[str]) -> dict[str, Any]:
        """The ``sheet_pair`` columns ``repos.replace_pairs`` inserts."""
        return {
            "before_frame_id": (
                before_ids[self.before_index] if self.before_index is not None else None
            ),
            "after_frame_id": (
                after_ids[self.after_index] if self.after_index is not None else None
            ),
            "status": self.status,
            "match_method": self.match_method,
            "score": self.score,
            "sort_key": self.sort_key,
            "warnings": list(self.warnings) or None,
        }


def pair_rows(
    pairs: list[PairRecord], before_ids: list[str], after_ids: list[str]
) -> list[dict[str, Any]]:
    """Every pair as a ``repos.replace_pairs`` payload, in matching order."""
    return [pair.to_row(before_ids, after_ids) for pair in pairs]


@lru_cache(maxsize=1)
def _packaged_frames_config() -> FramesConfig:
    """The shipped ``frames.yaml`` defaults, for a caller with no bundle open.

    Only the normalisation block is read here, and it is the same in every
    project unless someone edited it; a caller that has a bundle (the router)
    passes the project's own configuration instead.
    """
    return FramesConfig.model_validate(yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8")))


# --------------------------------------------------------------------------- keys


def natural_sort_key(text: str) -> str:
    """``A-101`` -> ``A-00000101``: digits zero-padded so numbers sort as numbers.

    A plain string sort puts ``A-101`` before ``A-99``, which is exactly the
    order a person reading the sheet list would call a bug. Padding rather than
    a tuple key because the value is stored in a Text column and sorted by
    SQLite (``repos.list_pairs`` orders by ``sort_key``).
    """
    return "".join(
        part.zfill(SORT_KEY_DIGITS) if part.isdigit() else part for part in _DIGITS_RE.split(text)
    )


def _frame_sort_key(frame: FrameRecord | None) -> str:
    if frame is None:
        return ""
    if frame.norm_key:
        return natural_sort_key(frame.norm_key)
    if frame.sheet_title:
        return natural_sort_key(frame.sheet_title)
    return natural_sort_key(f"{frame.file_name}:{frame.sort_index:04d}")


def _pair_sort_key(before: FrameRecord | None, after: FrameRecord | None) -> str:
    """Sheet number of the *after* sheet, falling back to the before sheet.

    The after set is the drawing as it is now, which is the list the user reads
    down; a removed sheet still has to appear in its own place, hence the
    fallback.
    """
    return _frame_sort_key(after) or _frame_sort_key(before)


def _title_tokens(frame: FrameRecord, frames_config: FramesConfig) -> frozenset[str]:
    """Normalised words of a drawing name.

    Split before normalisation, because ``normalize.strip_spaces`` removes the
    very separators the tokens are made of: `"1층 평면도 (A동)"` has to become
    three tokens, not one 12-character string.
    """
    if not frame.sheet_title:
        return frozenset()
    tokens = {
        normalize_key(token, frames_config) for token in _TITLE_SPLIT_RE.split(frame.sheet_title)
    }
    return frozenset(token for token in tokens if token)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


# --------------------------------------------------------------------------- status


def _matched_pair(
    before_index: int,
    after_index: int,
    before: FrameRecord,
    after: FrameRecord,
    *,
    method: str,
    score: float,
    extra_warnings: list[str] | None = None,
) -> PairRecord:
    """Wrap one accepted match, deciding the pre-comparison status.

    Three things are already knowable without opening the geometry: the two
    sides came from different converters (must not be compared -- the
    difference measured would be the converters', not the drawing's), the two
    files are byte-identical (nothing can have changed), or neither, which is
    the normal ``pending``.
    """
    warnings = list(extra_warnings or [])
    if _frame_sizes_differ(before, after):
        warnings.append("frame_size_differs")

    if before.converter and after.converter and before.converter != after.converter:
        status = STATUS_CONVERTER_MISMATCH
        warnings.append(f"converter:{before.converter}!={after.converter}")
    elif before.file_sha256 and before.file_sha256 == after.file_sha256:
        status = STATUS_SAME
    else:
        status = STATUS_PENDING

    return PairRecord(
        before_index=before_index,
        after_index=after_index,
        status=status,
        match_method=method,
        score=round(score, 3),
        sort_key=_pair_sort_key(before, after),
        warnings=sorted(set(warnings)),
    )


def manual_pair(
    before_index: int, after_index: int, before: FrameRecord, after: FrameRecord
) -> PairRecord:
    """One pairing the user made by hand on screen B (``match_method = manual``).

    Same pre-comparison status rules as an automatic match -- identical files
    are still ``same``, mismatched converters are still refused -- but with no
    score, because the user's judgement is not a similarity measurement
    (``sheet-pair.schema.json``: "Null for a manual pair").
    """
    record = _matched_pair(before_index, after_index, before, after, method="manual", score=0.0)
    record.score = None
    return record


def _frame_sizes_differ(before: FrameRecord, after: FrameRecord) -> bool:
    return not _sizes_within(before, after, POSITION_SIZE_TOLERANCE)


def _sizes_within(before: FrameRecord, after: FrameRecord, tolerance: float) -> bool:
    for left, right in ((before.width, after.width), (before.height, after.height)):
        reference = max(abs(left), abs(right))
        if reference <= 0:
            if abs(left - right) > 1e-9:
                return False
            continue
        if abs(left - right) / reference > tolerance:
            return False
    return True


# --------------------------------------------------------------------------- stages


def _match_unrecognized(
    before: list[FrameRecord],
    after: list[FrameRecord],
    open_before: set[int],
    open_after: set[int],
) -> list[PairRecord]:
    """Files that produced no title block, paired by file name (contract §3).

    They are never compared -- there is no frame to compare inside -- but they
    have to be visible, because "this drawing was not understood" is exactly
    what the user needs to see in order to pair it by hand or fix the file.
    """
    pairs: list[PairRecord] = []
    before_by_key: dict[str, list[int]] = {}
    after_by_key: dict[str, list[int]] = {}
    for index in sorted(open_before):
        if before[index].kind == KIND_UNRECOGNIZED:
            before_by_key.setdefault(before[index].norm_key, []).append(index)
    for index in sorted(open_after):
        if after[index].kind == KIND_UNRECOGNIZED:
            after_by_key.setdefault(after[index].norm_key, []).append(index)

    for key in sorted(set(before_by_key) | set(after_by_key)):
        befores = before_by_key.get(key, [])
        afters = after_by_key.get(key, [])
        for position in range(max(len(befores), len(afters))):
            b_index = befores[position] if position < len(befores) else None
            a_index = afters[position] if position < len(afters) else None
            pairs.append(
                PairRecord(
                    before_index=b_index,
                    after_index=a_index,
                    status=STATUS_UNRECOGNIZED,
                    match_method=None,
                    score=None,
                    sort_key=_pair_sort_key(
                        before[b_index] if b_index is not None else None,
                        after[a_index] if a_index is not None else None,
                    ),
                    warnings=[],
                )
            )
            if b_index is not None:
                open_before.discard(b_index)
            if a_index is not None:
                open_after.discard(a_index)
    return pairs


def _match_by_number(
    before: list[FrameRecord],
    after: list[FrameRecord],
    open_before: set[int],
    open_after: set[int],
    ambiguous_before: set[int],
    ambiguous_after: set[int],
) -> tuple[list[PairRecord], int]:
    """Stage 1. Returns the pairs and how many numbers were duplicated.

    A number that is not unique on both sides is *not* matched here: picking
    one of two identical numbers would silently compare the wrong sheets. Those
    frames drop through to the title and position stages, and are remembered as
    ambiguous so that if nothing else claims them they end up ``unpaired``
    rather than ``added``/``removed`` (brief Defaults for ambiguity). The count
    returned is every frame in a duplicated number group, on either side, which
    is what the summary reports as ``duplicate_sheet_no``.
    """
    pairs: list[PairRecord] = []
    before_by_key: dict[str, list[int]] = {}
    after_by_key: dict[str, list[int]] = {}
    for index in sorted(open_before):
        key = before[index].norm_key
        if key:
            before_by_key.setdefault(key, []).append(index)
    for index in sorted(open_after):
        key = after[index].norm_key
        if key:
            after_by_key.setdefault(key, []).append(index)

    duplicates = sum(
        len(indices)
        for mapping in (before_by_key, after_by_key)
        for indices in mapping.values()
        if len(indices) > 1
    )

    for key in sorted(set(before_by_key) & set(after_by_key)):
        befores = before_by_key[key]
        afters = after_by_key[key]
        if len(befores) != 1 or len(afters) != 1:
            # Only a collision that spans both sides makes a frame ambiguous:
            # the same number twice inside one set, with nothing to match on
            # the other side, is still a plain removal or addition.
            ambiguous_before.update(befores)
            ambiguous_after.update(afters)
            continue
        b_index, a_index = befores[0], afters[0]
        pairs.append(
            _matched_pair(
                b_index,
                a_index,
                before[b_index],
                after[a_index],
                method=METHOD_NUMBER,
                score=SCORE_NUMBER,
            )
        )
        open_before.discard(b_index)
        open_after.discard(a_index)

    return pairs, duplicates


def _numbers_disagree(before: FrameRecord, after: FrameRecord) -> bool:
    """Both sheets carry a drawing number, and the two numbers are different.

    Then they are different sheets, whatever their titles say, and title
    matching must not overrule that. ``match.title_jaccard_min`` is documented
    as the "minimum title similarity accepted **when there is no drawing
    number**" (``compare/config.py``), and this is what enforces it: stage 1
    already paired every number that agreed, so a pair that reaches stage 2
    with two different numbers is positive evidence *against* the match.

    It matters because drawing names are not distinctive. A whole set of sheets
    is called 1층 평면도, so a Jaccard of 1.0 between two of them says nothing;
    without this rule, R1-07's S14 (A-101 removed, A-103 added) would pair the
    removed sheet with the added one and hand R1-06 two unrelated drawings to
    diff. A genuinely renumbered sheet becomes ``removed`` + ``added`` instead
    and is paired by hand on screen B, which is a minute of the user's time
    rather than a page of invented changes.
    """
    return bool(before.norm_key and after.norm_key and before.norm_key != after.norm_key)


def _match_by_title(
    before: list[FrameRecord],
    after: list[FrameRecord],
    open_before: set[int],
    open_after: set[int],
    ambiguous_before: set[int],
    ambiguous_after: set[int],
    *,
    threshold: float,
    frames_config: FramesConfig,
) -> list[PairRecord]:
    """Stage 2: mutually-best title similarity above ``threshold``.

    "Mutually best" is what keeps this stage honest. Sheets in one set share
    most of their words (`평면도`, `1층`), so a one-directional best match would
    happily pair 1층 평면도 with 2층 평면도. Requiring each side to be the
    other's single best, with no tie, means an ambiguous group is handed to the
    user instead of guessed at.
    """
    b_tokens = {index: _title_tokens(before[index], frames_config) for index in open_before}
    a_tokens = {index: _title_tokens(after[index], frames_config) for index in open_after}

    scores: dict[tuple[int, int], float] = {}
    for b_index in sorted(open_before):
        for a_index in sorted(open_after):
            if _numbers_disagree(before[b_index], after[a_index]):
                continue
            score = _jaccard(b_tokens[b_index], a_tokens[a_index])
            if score >= threshold and score > 0.0:
                scores[(b_index, a_index)] = score

    by_before: dict[int, dict[int, float]] = {}
    by_after: dict[int, dict[int, float]] = {}
    for (b_index, a_index), score in scores.items():
        by_before.setdefault(b_index, {})[a_index] = score
        by_after.setdefault(a_index, {})[b_index] = score

    def _best(candidates: dict[int, float]) -> list[int]:
        if not candidates:
            return []
        top = max(candidates.values())
        return sorted(other for other, score in candidates.items() if score >= top - 1e-12)

    pairs: list[PairRecord] = []
    for b_index in sorted(open_before):
        best_after = _best(by_before.get(b_index, {}))
        if len(best_after) > 1:
            ambiguous_before.add(b_index)
            ambiguous_after.update(best_after)
            continue
        if not best_after:
            continue
        a_index = best_after[0]
        best_before = _best(by_after.get(a_index, {}))
        if len(best_before) > 1:
            ambiguous_after.add(a_index)
            ambiguous_before.update(best_before)
            continue
        if best_before[0] != b_index:
            continue
        pairs.append(
            _matched_pair(
                b_index,
                a_index,
                before[b_index],
                after[a_index],
                method=METHOD_TITLE,
                score=scores[(b_index, a_index)],
            )
        )
    for pair in pairs:
        if pair.before_index is not None:
            open_before.discard(pair.before_index)
        if pair.after_index is not None:
            open_after.discard(pair.after_index)
    return pairs


def _match_by_position(
    before: list[FrameRecord],
    after: list[FrameRecord],
    open_before: set[int],
    open_after: set[int],
    *,
    frames_config: FramesConfig,
) -> list[PairRecord]:
    """Stage 3: same file name, same reading position, same frame size +-1%.

    Same guard as stage 2: two sheets whose drawing numbers disagree are not
    the same sheet, however neatly they line up in the file
    (:func:`_numbers_disagree`). Position is the weakest of the three signals,
    so a printed number always outranks it.
    """
    by_file_after: dict[tuple[str, int], list[int]] = {}
    for index in sorted(open_after):
        key = (normalize_key(after[index].file_name, frames_config), after[index].sort_index)
        by_file_after.setdefault(key, []).append(index)

    pairs: list[PairRecord] = []
    for b_index in sorted(open_before):
        frame = before[b_index]
        key = (normalize_key(frame.file_name, frames_config), frame.sort_index)
        candidates = [index for index in by_file_after.get(key, []) if index in open_after]
        if len(candidates) != 1:
            continue
        a_index = candidates[0]
        if _numbers_disagree(frame, after[a_index]):
            continue
        if not _sizes_within(frame, after[a_index], POSITION_SIZE_TOLERANCE):
            continue
        pairs.append(
            _matched_pair(
                b_index,
                a_index,
                frame,
                after[a_index],
                method=METHOD_POSITION,
                score=SCORE_POSITION,
            )
        )
        open_before.discard(b_index)
        open_after.discard(a_index)
    return pairs


def _leftovers(
    before: list[FrameRecord],
    after: list[FrameRecord],
    open_before: set[int],
    open_after: set[int],
    ambiguous_before: set[int],
    ambiguous_after: set[int],
) -> list[PairRecord]:
    """Stage 4: ``removed`` / ``added``, or ``unpaired`` when it was ambiguous."""
    pairs: list[PairRecord] = []
    for index in sorted(open_before):
        status = STATUS_UNPAIRED if index in ambiguous_before else STATUS_REMOVED
        pairs.append(
            PairRecord(
                before_index=index,
                after_index=None,
                status=status,
                sort_key=_pair_sort_key(before[index], None),
            )
        )
    for index in sorted(open_after):
        status = STATUS_UNPAIRED if index in ambiguous_after else STATUS_ADDED
        pairs.append(
            PairRecord(
                before_index=None,
                after_index=index,
                status=status,
                sort_key=_pair_sort_key(None, after[index]),
            )
        )
    return pairs


# --------------------------------------------------------------------------- entry


@dataclass(frozen=True)
class MatchStats:
    """Counters the ``compare.frames`` job puts into ``compare_set.stats``."""

    duplicate_sheet_no: int = 0


def match_frames(
    before: list[FrameRecord],
    after: list[FrameRecord],
    config: CompareConfig,
    frames_config: FramesConfig | None = None,
) -> list[PairRecord]:
    """Pair the two sides' 도곽, ordered by sheet number (contract §6).

    ``frames_config`` supplies the normalisation used for titles and file
    names; it defaults to the packaged ``frames.yaml`` so a caller that only
    has ``compare.yaml`` still works, but the router always passes the
    project's own.
    """
    pairs, _ = match_frames_with_stats(before, after, config, frames_config)
    return pairs


def match_frames_with_stats(
    before: list[FrameRecord],
    after: list[FrameRecord],
    config: CompareConfig,
    frames_config: FramesConfig | None = None,
) -> tuple[list[PairRecord], MatchStats]:
    """:func:`match_frames` plus the counters worth reporting to the user."""
    frames_config = frames_config or _packaged_frames_config()
    open_before = set(range(len(before)))
    open_after = set(range(len(after)))
    ambiguous_before: set[int] = set()
    ambiguous_after: set[int] = set()

    pairs: list[PairRecord] = []
    pairs += _match_unrecognized(before, after, open_before, open_after)
    numbered, duplicates = _match_by_number(
        before, after, open_before, open_after, ambiguous_before, ambiguous_after
    )
    pairs += numbered
    pairs += _match_by_title(
        before,
        after,
        open_before,
        open_after,
        ambiguous_before,
        ambiguous_after,
        threshold=config.match.title_jaccard_min,
        frames_config=frames_config,
    )
    pairs += _match_by_position(before, after, open_before, open_after, frames_config=frames_config)
    pairs += _leftovers(before, after, open_before, open_after, ambiguous_before, ambiguous_after)

    pairs.sort(
        key=lambda pair: (
            pair.sort_key,
            pair.before_index if pair.before_index is not None else -1,
            pair.after_index if pair.after_index is not None else -1,
        )
    )
    return pairs, MatchStats(duplicate_sheet_no=duplicates)


__all__ = [
    "METHOD_NUMBER",
    "METHOD_POSITION",
    "METHOD_TITLE",
    "POSITION_SIZE_TOLERANCE",
    "SCORE_NUMBER",
    "SCORE_POSITION",
    "STATUS_ADDED",
    "STATUS_CONVERTER_MISMATCH",
    "STATUS_PENDING",
    "STATUS_REMOVED",
    "STATUS_SAME",
    "STATUS_UNPAIRED",
    "STATUS_UNRECOGNIZED",
    "MatchStats",
    "PairRecord",
    "manual_pair",
    "match_frames",
    "match_frames_with_stats",
    "natural_sort_key",
    "pair_rows",
]
