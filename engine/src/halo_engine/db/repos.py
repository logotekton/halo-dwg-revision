"""Thin repository functions over :mod:`halo_engine.db.models` (plain SQLAlchemy 2 Sessions).

Every function takes an already-open :class:`~sqlalchemy.orm.Session` and
commits its own unit of work -- callers (``api/routers/*.py``, ``api/jobs.py``)
never touch the ORM directly, only these functions and the pydantic view
models in :mod:`halo_engine.model`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from halo_engine.db.ids import new_ulid
from halo_engine.db.models import (
    ChangeRow,
    ClusterRow,
    CompareSetRow,
    DrawingFileRow,
    DrawingSetRow,
    ProjectRow,
    RunRow,
    SheetFrameRow,
    SheetPairRow,
    XrefLinkRow,
)
from halo_engine.ingest.xref import DEFAULT_IGNORE_PATTERNS


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_project(session: Session, *, name: str, bundle_path: str) -> ProjectRow:
    now = _now()
    row = ProjectRow(
        id=new_ulid(),
        name=name,
        bundle_path=bundle_path,
        created_at=now,
        updated_at=now,
        search_paths=[],
        # W3-06 addendum 3 / G1 답변: default exclusion list, set once at
        # project creation so every later import already has it.
        ignore_patterns=list(DEFAULT_IGNORE_PATTERNS),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_project(session: Session, project_id: str) -> ProjectRow | None:
    return session.get(ProjectRow, project_id)


def update_project_settings(
    session: Session,
    project_id: str,
    *,
    search_paths: list[str] | None = None,
    ignore_patterns: list[str] | None = None,
) -> ProjectRow:
    """Used by ``PUT /projects/{id}/search-paths`` and the import-settings
    endpoint (``api/routers/xrefs.py``) -- ``None`` leaves a field unchanged."""
    row = session.get(ProjectRow, project_id)
    if row is None:
        raise KeyError(f"project {project_id!r} not found")
    if search_paths is not None:
        row.search_paths = search_paths
    if ignore_patterns is not None:
        row.ignore_patterns = ignore_patterns
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def create_drawing_set(
    session: Session, *, project_id: str, label: str | None = None
) -> DrawingSetRow:
    row = DrawingSetRow(id=new_ulid(), project_id=project_id, label=label, created_at=_now())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_drawing_set(session: Session, drawing_set_id: str) -> DrawingSetRow | None:
    return session.get(DrawingSetRow, drawing_set_id)


def create_drawing_file(
    session: Session,
    *,
    drawing_set_id: str,
    original_path: str,
    original_name: str,
    sha256: str,
    format: str,
    import_status: str,
    is_xref: bool = False,
) -> DrawingFileRow:
    now = _now()
    row = DrawingFileRow(
        id=new_ulid(),
        drawing_set_id=drawing_set_id,
        original_path=original_path,
        original_name=original_name,
        sha256=sha256,
        format=format,
        import_status=import_status,
        is_xref=is_xref,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_drawing_file(session: Session, file_id: str) -> DrawingFileRow | None:
    return session.get(DrawingFileRow, file_id)


def get_drawing_file_by_sha256(
    session: Session, *, drawing_set_id: str, sha256: str
) -> DrawingFileRow | None:
    """Used to avoid registering the same XREF target DWG twice within one
    drawing-set when several hosts reference it (W3-06 addendum 1: the
    real set's 8 XREF targets are shared by up to 55+ hosts each)."""
    stmt = select(DrawingFileRow).where(
        DrawingFileRow.drawing_set_id == drawing_set_id, DrawingFileRow.sha256 == sha256
    )
    return session.scalars(stmt).first()


def list_files_for_set(session: Session, drawing_set_id: str) -> list[DrawingFileRow]:
    stmt = (
        select(DrawingFileRow)
        .where(DrawingFileRow.drawing_set_id == drawing_set_id)
        .order_by(DrawingFileRow.created_at)
    )
    return list(session.scalars(stmt))


def update_drawing_file(session: Session, file_id: str, **fields: Any) -> DrawingFileRow:
    row = session.get(DrawingFileRow, file_id)
    if row is None:
        raise KeyError(f"drawing_file {file_id!r} not found")
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def add_xref_link(
    session: Session,
    *,
    host_file_id: str,
    block_name: str,
    declared_path: str,
    resolved_path: str | None,
    status: str,
) -> XrefLinkRow:
    row = XrefLinkRow(
        id=new_ulid(),
        host_file_id=host_file_id,
        block_name=block_name,
        declared_path=declared_path,
        resolved_path=resolved_path,
        status=status,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def list_xref_links_for_file(session: Session, host_file_id: str) -> list[XrefLinkRow]:
    stmt = (
        select(XrefLinkRow)
        .where(XrefLinkRow.host_file_id == host_file_id)
        .order_by(XrefLinkRow.block_name)
    )
    return list(session.scalars(stmt))


def replace_xref_links(
    session: Session, *, host_file_id: str, links: list[dict[str, str | None]]
) -> list[XrefLinkRow]:
    """Deletes every existing ``xref_link`` row for ``host_file_id`` and inserts
    ``links`` fresh -- called once per finished (or re-run) import of that
    host, so a re-import after adding a search path does not leave stale
    UNRESOLVED rows sitting next to the new RESOLVED ones for the same block.
    Each item: ``{block_name, declared_path, resolved_path, status}``.
    """
    session.query(XrefLinkRow).filter(XrefLinkRow.host_file_id == host_file_id).delete()
    rows = [
        XrefLinkRow(
            id=new_ulid(),
            host_file_id=host_file_id,
            block_name=str(link["block_name"]),
            declared_path=str(link["declared_path"]),
            resolved_path=link.get("resolved_path"),
            status=str(link["status"]),
        )
        for link in links
    ]
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


# ---------------------------------------------------------------------------
# R1 revision comparison (docs/contracts/r1.md §3)
#
# The `replace_*` functions are the shape the pipeline actually needs: a stage
# recomputes a whole level -- every frame of one side, every pair of a set,
# every change of a pair -- and writing it as "delete then insert" is what keeps
# a re-run from leaving yesterday's rows sitting next to today's. Each takes
# plain dicts, so the caller (compare/frames.py, compare/diff.py, ...) does not
# have to import the ORM.
# ---------------------------------------------------------------------------


def _assign(row: Any, fields: dict[str, Any], *, what: str) -> None:
    """Set ``fields`` on ``row``, refusing a name the table does not have.

    A typo in a keyword would otherwise attach an attribute to the instance and
    vanish at commit, which is exactly the silent-drift failure the contract's
    fixed column list exists to prevent.
    """
    for key, value in fields.items():
        if not hasattr(type(row), key):
            raise KeyError(f"{what} has no column {key!r}")
        setattr(row, key, value)


def create_compare_set(
    session: Session,
    *,
    project_id: str,
    before_set_id: str,
    after_set_id: str,
    run_date: str,
    status: str = "ingesting",
    options: dict[str, Any] | None = None,
) -> CompareSetRow:
    """Start a comparison. ``run_date`` is ``YYYY-MM-DD`` from the renderer, never the clock."""
    now = _now()
    row = CompareSetRow(
        id=new_ulid(),
        project_id=project_id,
        before_set_id=before_set_id,
        after_set_id=after_set_id,
        run_date=run_date,
        status=status,
        options=options or {},
        stats=None,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_compare_set(session: Session, compare_set_id: str) -> CompareSetRow | None:
    return session.get(CompareSetRow, compare_set_id)


def update_compare_set(session: Session, compare_set_id: str, **fields: Any) -> CompareSetRow:
    """Set any of ``status``, ``options``, ``stats``, ``run_date``; bumps ``updated_at``."""
    row = session.get(CompareSetRow, compare_set_id)
    if row is None:
        raise KeyError(f"compare_set {compare_set_id!r} not found")
    _assign(row, fields, what="compare_set")
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def list_compare_sets(session: Session, *, project_id: str | None = None) -> list[CompareSetRow]:
    """Newest first, which is the order screen A lists them in."""
    stmt = select(CompareSetRow).order_by(CompareSetRow.created_at.desc())
    if project_id is not None:
        stmt = stmt.where(CompareSetRow.project_id == project_id)
    return list(session.scalars(stmt))


def replace_frames(
    session: Session,
    compare_set_id: str,
    role: str,
    frames: list[dict[str, Any]],
) -> list[SheetFrameRow]:
    """Replace one side's title blocks.

    Every pair of the compare set goes with them (and every change and cluster
    below those pairs): a pair is identified by two frame ids, so re-extracting
    frames invalidates the matching that produced it. Each item carries the
    ``sheet_frame`` columns except ``id`` and ``compare_set_id``/``role``,
    which are filled in here.
    """
    _delete_pairs_of_set(session, compare_set_id)
    session.query(SheetFrameRow).filter(
        SheetFrameRow.compare_set_id == compare_set_id, SheetFrameRow.role == role
    ).delete()
    rows = [
        SheetFrameRow(id=new_ulid(), compare_set_id=compare_set_id, role=role, **frame)
        for frame in frames
    ]
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def list_frames(
    session: Session, compare_set_id: str, *, role: str | None = None
) -> list[SheetFrameRow]:
    """Ordered by ``norm_key`` then ``sort_index`` -- the sheet list's own order."""
    stmt = (
        select(SheetFrameRow)
        .where(SheetFrameRow.compare_set_id == compare_set_id)
        .order_by(SheetFrameRow.norm_key, SheetFrameRow.sort_index)
    )
    if role is not None:
        stmt = stmt.where(SheetFrameRow.role == role)
    return list(session.scalars(stmt))


def _delete_pairs_of_set(session: Session, compare_set_id: str) -> None:
    pair_ids = list(
        session.scalars(
            select(SheetPairRow.id).where(SheetPairRow.compare_set_id == compare_set_id)
        )
    )
    for pair_id in pair_ids:
        _delete_pair_children(session, pair_id)
    session.query(SheetPairRow).filter(SheetPairRow.compare_set_id == compare_set_id).delete()


def _delete_pair_children(session: Session, pair_id: str) -> None:
    session.query(ChangeRow).filter(ChangeRow.pair_id == pair_id).delete()
    session.query(ClusterRow).filter(ClusterRow.pair_id == pair_id).delete()


def replace_pairs(
    session: Session, compare_set_id: str, pairs: list[dict[str, Any]]
) -> list[SheetPairRow]:
    """Replace the whole matching of a compare set, changes and clusters included.

    Each item carries the ``sheet_pair`` columns except ``id``,
    ``compare_set_id`` and the timestamps.
    """
    _delete_pairs_of_set(session, compare_set_id)
    now = _now()
    rows = [
        SheetPairRow(
            id=new_ulid(),
            compare_set_id=compare_set_id,
            created_at=now,
            updated_at=now,
            **pair,
        )
        for pair in pairs
    ]
    session.add_all(rows)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def list_pairs(
    session: Session, compare_set_id: str, *, status: str | None = None
) -> list[SheetPairRow]:
    """Ordered by ``sort_key``, which is the sheet number the user reads."""
    stmt = (
        select(SheetPairRow)
        .where(SheetPairRow.compare_set_id == compare_set_id)
        .order_by(SheetPairRow.sort_key, SheetPairRow.id)
    )
    if status is not None:
        stmt = stmt.where(SheetPairRow.status == status)
    return list(session.scalars(stmt))


def get_pair(session: Session, pair_id: str) -> SheetPairRow | None:
    return session.get(SheetPairRow, pair_id)


def update_pair(session: Session, pair_id: str, **fields: Any) -> SheetPairRow:
    """Set any ``sheet_pair`` column (status, counts, artefact paths, warnings)."""
    row = session.get(SheetPairRow, pair_id)
    if row is None:
        raise KeyError(f"sheet_pair {pair_id!r} not found")
    _assign(row, fields, what="sheet_pair")
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def create_manual_pair(
    session: Session,
    *,
    compare_set_id: str,
    before_frame_id: str,
    after_frame_id: str,
    sort_key: str | None = None,
) -> SheetPairRow:
    """Pair two frames by hand (screen B), replacing whatever they were in before.

    Any existing pair that mentions either frame is removed first: the user is
    saying these two belong together, and leaving the ``unpaired`` rows behind
    would count the same sheet twice in the summary. ``sort_key`` defaults to
    the after frame's ``norm_key``.
    """
    stale = list(
        session.scalars(
            select(SheetPairRow).where(
                SheetPairRow.compare_set_id == compare_set_id,
                (SheetPairRow.before_frame_id.in_([before_frame_id, after_frame_id]))
                | (SheetPairRow.after_frame_id.in_([before_frame_id, after_frame_id])),
            )
        )
    )
    for pair in stale:
        _delete_pair_children(session, pair.id)
        session.delete(pair)

    if sort_key is None:
        after_frame = session.get(SheetFrameRow, after_frame_id)
        sort_key = after_frame.norm_key if after_frame is not None else ""

    now = _now()
    row = SheetPairRow(
        id=new_ulid(),
        compare_set_id=compare_set_id,
        before_frame_id=before_frame_id,
        after_frame_id=after_frame_id,
        status="pending",
        match_method="manual",
        score=None,
        sort_key=sort_key,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def delete_pair(session: Session, pair_id: str, *, manual_only: bool = True) -> None:
    """Remove a pair and everything under it.

    ``DELETE /compare/pairs/{pair_id}`` only undoes a pairing the user made, so
    by default this refuses a pair the matcher produced -- undoing that would
    silently drop a sheet from the comparison.
    """
    row = session.get(SheetPairRow, pair_id)
    if row is None:
        raise KeyError(f"sheet_pair {pair_id!r} not found")
    if manual_only and row.match_method != "manual":
        raise ValueError(f"sheet_pair {pair_id!r} was matched by {row.match_method!r}, not by hand")
    _delete_pair_children(session, pair_id)
    session.delete(row)
    session.commit()


def replace_changes(
    session: Session, pair_id: str, changes: list[dict[str, Any]]
) -> list[ChangeRow]:
    """Replace a pair's changes and refresh its ``change_count``/``minor_count``.

    The counters are derived here rather than left to the caller: they are what
    the sheet list shows, and a stale count is indistinguishable from a real
    one. Each item carries the ``change`` columns except ``id`` and ``pair_id``.
    """
    session.query(ChangeRow).filter(ChangeRow.pair_id == pair_id).delete()
    rows = [ChangeRow(id=new_ulid(), pair_id=pair_id, **change) for change in changes]
    session.add_all(rows)
    pair = session.get(SheetPairRow, pair_id)
    if pair is not None:
        pair.change_count = len(rows)
        pair.minor_count = sum(1 for row in rows if row.minor)
        pair.updated_at = _now()
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def list_changes(session: Session, pair_id: str) -> list[ChangeRow]:
    """Ascending by ``seq`` -- the order the sidecar writes and the ids follow."""
    stmt = select(ChangeRow).where(ChangeRow.pair_id == pair_id).order_by(ChangeRow.seq)
    return list(session.scalars(stmt))


def replace_clusters(
    session: Session,
    pair_id: str,
    clusters: list[dict[str, Any]],
    keep_decisions: bool = True,
) -> list[ClusterRow]:
    """Replace a pair's clusters, carrying the user's review over by ``signature``.

    Re-running a comparison recomputes every cluster from scratch, so the row
    ids and often the numbers change. What must not change is the work the user
    already did: a new cluster whose ``signature`` matches an old one inherits
    its ``decision``, ``user_label`` and ``note``
    (``docs/contracts/compare-dxf.md`` §7). A cluster the incoming payload
    already decided for itself keeps its own value -- carry-over only fills in
    what is still ``pending``/empty. Pass ``keep_decisions=False`` to start the
    review over.

    Each item carries the ``cluster`` columns except ``id``, ``pair_id`` and
    ``updated_at``. Also refreshes the pair's ``cluster_count``.
    """
    carried: dict[str, tuple[str, str | None, str | None]] = {}
    if keep_decisions:
        for old in session.scalars(select(ClusterRow).where(ClusterRow.pair_id == pair_id)):
            carried[old.signature] = (old.decision, old.user_label, old.note)

    session.query(ClusterRow).filter(ClusterRow.pair_id == pair_id).delete()

    now = _now()
    rows: list[ClusterRow] = []
    for cluster in clusters:
        fields = dict(cluster)
        previous = carried.get(str(fields.get("signature", "")))
        if previous is not None:
            decision, user_label, note = previous
            if fields.get("decision", "pending") == "pending":
                fields["decision"] = decision
            if fields.get("user_label") is None:
                fields["user_label"] = user_label
            if fields.get("note") is None:
                fields["note"] = note
        rows.append(ClusterRow(id=new_ulid(), pair_id=pair_id, updated_at=now, **fields))

    session.add_all(rows)
    pair = session.get(SheetPairRow, pair_id)
    if pair is not None:
        pair.cluster_count = len(rows)
        pair.updated_at = now
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def list_clusters(session: Session, pair_id: str) -> list[ClusterRow]:
    """Ascending by ``number`` -- badge order, and revision-table row order."""
    stmt = select(ClusterRow).where(ClusterRow.pair_id == pair_id).order_by(ClusterRow.number)
    return list(session.scalars(stmt))


def get_cluster_by_number(session: Session, pair_id: str, number: int) -> ClusterRow | None:
    """The API addresses a cluster by its badge number, never by its ULID."""
    stmt = select(ClusterRow).where(ClusterRow.pair_id == pair_id, ClusterRow.number == number)
    return session.scalars(stmt).first()


def update_cluster(session: Session, pair_id: str, number: int, **fields: Any) -> ClusterRow:
    """Record the user's review: ``decision``, ``user_label``, ``note``.

    Named fields are passed through as given, so ``note=None`` clears the memo
    rather than leaving it alone -- ``PATCH`` bodies omit what they do not touch.
    """
    row = get_cluster_by_number(session, pair_id, number)
    if row is None:
        raise KeyError(f"cluster {number} of sheet_pair {pair_id!r} not found")
    _assign(row, fields, what="cluster")
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def create_run(
    session: Session,
    *,
    compare_set_id: str,
    run_date: str,
    layer_name: str,
    output_dir: str,
    scope: str = "all",
    method: str = "auto",
    pair_ids: list[str] | None = None,
    approved_count: int = 0,
    ignored_count: int = 0,
    files: list[dict[str, Any]] | None = None,
    status: str = "running",
) -> RunRow:
    """Open a run row before the export job starts, so a crash leaves a trace."""
    row = RunRow(
        id=new_ulid(),
        compare_set_id=compare_set_id,
        run_date=run_date,
        layer_name=layer_name,
        output_dir=output_dir,
        scope=scope,
        method=method,
        pair_ids=pair_ids or [],
        approved_count=approved_count,
        ignored_count=ignored_count,
        files=files or [],
        status=status,
        created_at=_now(),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def update_run(session: Session, run_id: str, **fields: Any) -> RunRow:
    """Set any ``run`` column -- the export job closes the row with ``status`` and ``files``."""
    row = session.get(RunRow, run_id)
    if row is None:
        raise KeyError(f"run {run_id!r} not found")
    _assign(row, fields, what="run")
    session.commit()
    session.refresh(row)
    return row


def list_runs(session: Session, compare_set_id: str) -> list[RunRow]:
    """Newest first: screen D shows the last export at the top."""
    stmt = (
        select(RunRow)
        .where(RunRow.compare_set_id == compare_set_id)
        .order_by(RunRow.created_at.desc(), RunRow.id.desc())
    )
    return list(session.scalars(stmt))


def get_run(session: Session, run_id: str) -> RunRow | None:
    return session.get(RunRow, run_id)


__all__ = [
    "add_xref_link",
    "create_compare_set",
    "create_drawing_file",
    "create_drawing_set",
    "create_manual_pair",
    "create_project",
    "create_run",
    "delete_pair",
    "get_cluster_by_number",
    "get_compare_set",
    "get_drawing_file",
    "get_drawing_file_by_sha256",
    "get_drawing_set",
    "get_pair",
    "get_project",
    "get_run",
    "list_changes",
    "list_clusters",
    "list_compare_sets",
    "list_files_for_set",
    "list_frames",
    "list_pairs",
    "list_runs",
    "list_xref_links_for_file",
    "replace_changes",
    "replace_clusters",
    "replace_frames",
    "replace_pairs",
    "replace_xref_links",
    "update_cluster",
    "update_compare_set",
    "update_drawing_file",
    "update_pair",
    "update_project_settings",
    "update_run",
]
