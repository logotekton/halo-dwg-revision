"""출력: the ``compare.export`` job -- markup drawings, ``changes.tsv``, ``run.json``.

This is the last step of the app and the only one that writes outside the
bundle. Everything before it produced review material; this produces the files
a person hands over:

``<프로젝트>/출력/<YYYY-MM-DD>[-n]/``
    ``<도면번호>_<후 라벨>_markup.dwg`` (or ``.dxf``), one per 도곽 with an
    approved cluster; ``changes.tsv``, the change list for Excel, which also
    carries the 무시 rows; ``run.json``, the record of what this export
    produced (schema ``compare/run``).

Four decisions shape the module.

**The date names the folder, and a second export never overwrites the first.**
``출력/2026-09-04/`` exists? Then this run is ``출력/2026-09-04-2/`` and its
layer is ``REV-20260904-2`` (contract §11). Re-exporting after fixing one
sheet's review is normal, and losing the copy that was already sent out is not
recoverable.

**How the DWG gets written is a fallback chain, not a setting.** ``auto`` means
background ZWCAD when this machine has it (contract §6.1) and a plain ``.dxf``
in the output folder when it does not, so a macOS developer or a PC without
ZWCAD still gets a usable, openable result instead of an error. ``acad-ts`` is
only ever used when ``compare.yaml`` names it: its DWG writer drops INSERTs
whose block and layer share a name, which is exactly what a title block is
(``packages/acad-bridge/README.md``, "Known acad-ts gaps" #1), and a drawing
that silently loses its title block must not be produced by a default.

**One ZWCAD instance, one thread.** The COM object is STA: it may only be used
from the thread that created it (``compare/zwcad.py``), so the converter is
created on a dedicated single-worker ``ThreadPoolExecutor`` and every file goes
through the same one -- the same shape ``compare/ingest_set.py`` uses for the
inbound conversion.

**Nothing outside the bundle and the output folder is written.** Every write
goes through ``bundle.guard.assert_writable_path`` with those two roots
(CLAUDE.md rule 1). The 전·후 source folders are read and nothing else.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any

from halo_engine.api import jobs as jobs_mod
from halo_engine.bundle.create import BundleHandle
from halo_engine.bundle.guard import assert_writable_path
from halo_engine.compare import compare_dxf as compare_dxf_mod
from halo_engine.compare import markup as markup_mod
from halo_engine.compare import zwcad
from halo_engine.compare.config import CompareConfig, load_compare_config
from halo_engine.compare.frames import FrameRecord
from halo_engine.db import repos
from halo_engine.db.models import ClusterRow, RunRow, SheetFrameRow, SheetPairRow

logger = logging.getLogger("halo_engine.compare.export")

#: Contract version of ``run.json``.
SCHEMA_VERSION = "0.1"

CHANGES_TSV_NAME = "changes.tsv"
RUN_JSON_NAME = "run.json"

#: ``changes.tsv`` header (brief R1-09 §2). Tab separated, UTF-8 without a BOM,
#: LF line endings -- the format the ledger asked for.
TSV_COLUMNS = ["도면번호", "도면명", "번호", "종류", "내용", "판정", "일자"]
TSV_ENCODING = "utf-8"

#: ``run.files[].writer`` (``compare/run.schema.json``): what actually wrote the file.
WRITER_ZWCAD = "zwcad-com"
WRITER_ACAD_TS = "acad-ts"
WRITER_DXF_ONLY = "dxf-only"

#: Warning codes collected into ``compare_set.stats['export']`` and broadcast
#: with the job's progress. ``run.json`` has no room for them by schema.
WARN_ZWCAD_UNAVAILABLE = "zwcad_unavailable"
WARN_ZWCAD_FAILED = "zwcad_failed"
WARN_ACAD_TS_UNAVAILABLE = "acad_ts_unavailable"
WARN_ACAD_TS_FAILED = "acad_ts_failed"
WARN_ACAD_TS_TITLEBLOCK = "acad_ts_titleblock_risk"
WARN_DUPLICATE_FILE_NAME = "duplicate_file_name"

#: ``sheet_pair.status`` values that cannot produce an export: they were never
#: compared, so they have no clusters to approve.
UNEXPORTABLE_PAIR_STATUSES = frozenset({"added", "removed", "unrecognized", "converter_mismatch"})

#: 판정 as the TSV prints it. ``pending`` never reaches the list: a cluster
#: nobody decided on is not a result.
DECISION_LABELS = {"approved": "승인", "ignored": "무시"}

#: ``cluster.kind`` (contract §3) in the words the 변경 리스트 uses. The engine
#: already writes Korean into ``cluster.label`` (``compare/labels.py``); this is
#: the same document, not a UI string (CLAUDE.md rule 8).
KIND_LABELS = {
    "added": "신설",
    "removed": "삭제",
    "modified": "수정",
    "moved": "이동",
    "text": "문구",
    "dimension": "치수",
    "blockdef": "블록 정의",
    "mixed": "혼합",
}

#: Characters no Windows file name may contain, folded to ``_`` (brief §2).
_ILLEGAL_FILE_CHARS = '<>:"/\\|?*'

#: engine/src/halo_engine/compare/export.py -> compare -> halo_engine -> src -> engine -> root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_ACAD_BRIDGE_BIN = _REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"

#: Seconds one ``acad-bridge dxf2dwg`` call may take. Generous: the bridge is a
#: Node process that reads and rewrites a whole drawing.
ACAD_TS_TIMEOUT_S = 300.0


# --------------------------------------------------------------------------- output folder


def resolve_output_dir(project_dir: Path, run_date: str, config: CompareConfig) -> tuple[Path, str]:
    """``<프로젝트>/출력/<run_date>`` and its layer name, or the next free ``-n``.

    Contract §11: exporting twice on the same date does not overwrite. The
    suffix is decided by counting the folders that are already there and it is
    applied to the layer as well, so a drawing that was marked up twice in one
    day carries two distinguishable revision layers rather than one layer with
    both days' clouds on it.
    """
    base = project_dir / config.output.dir_name
    first = base / run_date
    if not first.exists():
        return first, config.revision_layer(run_date)
    suffix = 2
    while (base / f"{run_date}-{suffix}").exists():
        suffix += 1
    return base / f"{run_date}-{suffix}", config.revision_layer(run_date, suffix=suffix)


def sanitize_file_name(name: str) -> str:
    """Fold anything Windows refuses in a file name to ``_`` (brief §2).

    Drawing numbers really do contain slashes (``A-101/2``), and control
    characters can arrive from a badly converted ATTRIB.
    """
    cleaned = "".join(
        "_" if char in _ILLEGAL_FILE_CHARS or ord(char) < 32 else char for char in name
    )
    return cleaned.strip().rstrip(".") or "_"


def markup_file_stem(config: CompareConfig, *, sheet_no: str, after_label: str) -> str:
    """``output.file_pattern`` filled in and made safe for a file system."""
    stem = config.output.file_pattern.format(sheet_no=sheet_no, after_label=after_label)
    return sanitize_file_name(stem)


# --------------------------------------------------------------------------- change list


@dataclass(frozen=True)
class ChangeListRow:
    """One line of ``changes.tsv``: one decided cluster of one sheet."""

    sheet_no: str
    sheet_title: str
    number: int
    kind: str
    content: str
    decision: str
    run_date: str

    def cells(self) -> list[str]:
        return [
            self.sheet_no,
            self.sheet_title,
            str(self.number),
            KIND_LABELS.get(self.kind, self.kind),
            self.content,
            DECISION_LABELS.get(self.decision, self.decision),
            self.run_date,
        ]


def _tsv_cell(value: str) -> str:
    """A tab or a newline inside a value would invent a column or a row."""
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def write_changes_tsv(
    rows: list[ChangeListRow], path: Path, *, allowed_roots: list[Path] | None = None
) -> Path:
    """Write the 변경 리스트 (brief §2).

    UTF-8 **without** a BOM and LF line endings, written as bytes so the
    platform's own newline translation cannot turn them into CRLF: the file has
    to be byte-identical on the Windows install and on a developer's machine.
    Both 승인 and 무시 rows are here -- the 판정 column is what distinguishes
    them, and a reviewer who ignored a change still has to be able to show that
    the change was seen (brief Defaults for ambiguity).
    """
    lines = ["\t".join(TSV_COLUMNS)]
    lines.extend("\t".join(_tsv_cell(cell) for cell in row.cells()) for row in rows)
    payload = ("\n".join(lines) + "\n").encode(TSV_ENCODING)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_path(path, allowed_roots=allowed_roots or [path.parent])
    path.write_bytes(payload)
    return path


# --------------------------------------------------------------------------- run.json


def run_payload(row: RunRow, *, for_disk: bool) -> dict[str, Any]:
    """The ``Run`` document (``compare/run.schema.json``).

    Two shapes of the same record. ``for_disk`` is ``run.json``: it carries
    ``schema_version`` and names its files *relative to the folder it sits in*,
    so the whole output folder can be zipped, copied to a site PC or attached to
    a mail and still describe itself (brief Defaults for ambiguity). The API
    shape carries the absolute paths screen D opens and the row's own
    ``created_at``, which is a database timestamp rather than part of the
    deterministic output (contract §11).
    """
    output_dir = Path(row.output_dir)
    files = []
    for entry in row.files or []:
        path = Path(str(entry.get("path", "")))
        if for_disk:
            try:
                shown = path.relative_to(output_dir).as_posix()
            except ValueError:
                shown = path.name
        else:
            shown = str(path)
        files.append(
            {
                "pair_id": entry.get("pair_id"),
                "sheet_no": entry.get("sheet_no"),
                "path": shown,
                "format": entry.get("format"),
                "writer": entry.get("writer"),
            }
        )

    payload: dict[str, Any] = {}
    if for_disk:
        payload["schema_version"] = SCHEMA_VERSION
    payload.update(
        {
            "id": row.id,
            "compare_set_id": row.compare_set_id,
            "run_date": row.run_date,
            "layer_name": row.layer_name,
            "output_dir": str(output_dir),
            "scope": row.scope,
            "method": row.method,
            "pair_ids": list(row.pair_ids or []),
            "approved_count": int(row.approved_count or 0),
            "ignored_count": int(row.ignored_count or 0),
            "files": files,
            "status": row.status,
            "error_message": row.error_message,
        }
    )
    if not for_disk and row.created_at is not None:
        payload["created_at"] = row.created_at.replace(tzinfo=UTC).isoformat()
    return payload


def write_run_json(row: RunRow, path: Path, *, allowed_roots: list[Path] | None = None) -> Path:
    """``run.json`` next to the drawings: UTF-8, two-space indent, LF, trailing newline."""
    text = json.dumps(run_payload(row, for_disk=True), ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_path(path, allowed_roots=allowed_roots or [path.parent])
    path.write_bytes((text + "\n").encode("utf-8"))
    return path


# --------------------------------------------------------------------------- the worker


@dataclass(frozen=True)
class MarkupTask:
    """One sheet's markup, as it crosses into the process pool (contract §6.2).

    Every field is a built-in or a picklable dataclass; no ezdxf document ever
    crosses the boundary, the same rule ``compare_dxf.ComparePairInput`` follows.
    """

    pair_id: str
    sheet_no: str | None
    after_working_dxf: str
    frame: FrameRecord
    clusters: list[dict[str, Any]]
    run_date: str
    layer_name: str
    out_path: str
    bundle_root: str


@dataclass
class MarkupPairOutput:
    """What one worker hands back for one sheet. Never an exception."""

    pair_id: str
    path: str | None = None
    numbers: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_s: float = 0.0


def markup_pair(task: MarkupTask, config: CompareConfig) -> MarkupPairOutput:
    """Build one sheet's ``markup.dxf``. The unit of work the process pool runs.

    A sheet that fails comes back with ``error`` set rather than raising: one
    unreadable drawing out of 68 must not cost the other 67 their markup, the
    same rule the comparison itself follows.
    """
    started = time.perf_counter()
    output = MarkupPairOutput(pair_id=task.pair_id)
    try:
        result = markup_mod.write_markup_dxf(
            after_working_dxf=Path(task.after_working_dxf),
            clusters=task.clusters,
            frame=task.frame,
            run_date=task.run_date,
            layer_name=task.layer_name,
            config=config,
            out_path=Path(task.out_path),
            allowed_roots=[Path(task.bundle_root)],
        )
        if result is not None:
            output.path = str(result.path)
            output.numbers = list(result.numbers)
            output.warnings = list(result.warnings)
    except Exception as error:  # noqa: BLE001 - one bad sheet must not fail the run
        logger.exception("markup failed for pair %s", task.pair_id)
        output.error = f"{type(error).__name__}: {error}"
    output.elapsed_s = round(time.perf_counter() - started, 3)
    return output


# --------------------------------------------------------------------------- DWG writers


def resolve_acad_bridge_bin(settings: Any) -> Path | None:
    """``packages/acad-bridge/bin/acad-bridge.mjs``, or ``None`` when it is not built."""
    candidate = getattr(settings, "acad_bridge_bin", None) or _DEFAULT_ACAD_BRIDGE_BIN
    return candidate if Path(candidate).is_file() else None


def effective_method(requested: str, config: CompareConfig) -> str:
    """``run.method``: what the request asked for, else ``output.dwg_writer``.

    A request that says ``auto`` is not an opinion -- it is the renderer's
    default -- so the project's own setting decides. An explicit ``zwcad`` /
    ``acad-ts`` / ``dxf-only`` in the request wins over the file.
    """
    if requested and requested != "auto":
        return requested
    return config.output.dwg_writer


def choose_writer(
    method: str, *, zwcad_available: bool, acad_bridge_bin: Path | None
) -> tuple[str, list[str]]:
    """Which writer this run will use, and what to warn about (brief §2).

    ``auto`` and an explicit ``zwcad`` behave the same when ZWCAD is missing:
    the run still produces every markup drawing, as ``.dxf``, and says so. A
    run that refused to produce anything because the office PC has no ZWCAD
    would leave the reviewer with nothing to show for the review they just did.
    """
    if method in {"auto", "zwcad"}:
        if zwcad_available:
            return WRITER_ZWCAD, []
        return WRITER_DXF_ONLY, [WARN_ZWCAD_UNAVAILABLE]
    if method == WRITER_ACAD_TS:
        if acad_bridge_bin is not None:
            return WRITER_ACAD_TS, [WARN_ACAD_TS_TITLEBLOCK]
        return WRITER_DXF_ONLY, [WARN_ACAD_TS_UNAVAILABLE]
    return WRITER_DXF_ONLY, []


def copy_as_dxf(markup_dxf: Path, out_path: Path, *, allowed_roots: list[Path]) -> Path:
    """The no-DWG-writer path: the markup DXF itself, in the output folder."""
    assert_writable_path(out_path, allowed_roots=allowed_roots)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(markup_dxf, out_path)
    return out_path


def convert_with_acad_ts(
    bridge_bin: Path, markup_dxf: Path, out_path: Path, *, allowed_roots: list[Path]
) -> None:
    """``acad-bridge dxf2dwg``. Only reached when ``compare.yaml`` asked for it."""
    assert_writable_path(out_path, allowed_roots=allowed_roots)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["node", str(bridge_bin), "dxf2dwg", str(markup_dxf), str(out_path)],
        capture_output=True,
        text=True,
        timeout=ACAD_TS_TIMEOUT_S,
        check=False,
    )
    if completed.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            f"acad-bridge dxf2dwg failed ({completed.returncode}): "
            f"{(completed.stderr or completed.stdout or '').strip()[:400]}"
        )


# --------------------------------------------------------------------------- gathering


@dataclass
class _SheetPlan:
    """One 도곽 짝 as the export sees it: where its drawing is and what was decided."""

    pair: SheetPairRow
    frame: SheetFrameRow
    frame_record: FrameRecord
    working_dxf: Path
    sheet_no: str
    sheet_title: str
    clusters: list[dict[str, Any]]

    @property
    def approved(self) -> list[dict[str, Any]]:
        return markup_mod.approved_clusters(self.clusters)

    @property
    def decided(self) -> list[dict[str, Any]]:
        return sorted(
            (cluster for cluster in self.clusters if cluster.get("decision") in DECISION_LABELS),
            key=lambda cluster: int(cluster["number"]),
        )


def _frame_record(row: SheetFrameRow) -> FrameRecord:
    """A ``sheet_frame`` row back as the picklable record the engine works with."""
    return FrameRecord(
        file_id=row.file_id,
        kind=row.kind,
        titleblock_handle=row.titleblock_handle,
        block_name=row.block_name,
        bbox=list(row.bbox or []),
        sheet_no=row.sheet_no,
        sheet_title=row.sheet_title,
        scale_text=row.scale_text,
        scale_denominator=row.scale_denominator,
        date_text=row.date_text,
        norm_key=row.norm_key,
        sort_index=row.sort_index,
        entity_handles=list(row.entity_handles or []),
        provenance=dict(row.provenance or {}),
        attributes=dict(row.attributes or {}),
        role=row.role,
    )


def _cluster_dict(row: ClusterRow) -> dict[str, Any]:
    """A ``cluster`` row in sidecar shape, for a pair whose ``clusters.json`` is gone."""
    return {
        "id": f"c{row.number}",
        "number": row.number,
        "bbox": list(row.bbox or []),
        "kind": row.kind,
        "label": row.label,
        "user_label": row.user_label,
        "decision": row.decision,
        "note": row.note,
        "cloud": dict(row.cloud or {}),
        "badge": dict(row.badge or {}),
    }


def _pair_clusters(bundle: BundleHandle, pair: SheetPairRow) -> list[dict[str, Any]]:
    """This pair's clusters with the review merged in (contract §7).

    ``clusters.json`` is the record of the comparison -- it carries the cloud
    polyline the markup must reproduce verbatim -- and the ``cluster`` table is
    the record of the review. The export needs both, so it reads the file and
    overlays the rows, exactly as ``GET /compare/pairs/{id}/clusters`` does.
    """
    with bundle.session_factory() as session:
        rows = repos.list_clusters(session, pair.id)
    path = (
        Path(pair.clusters_json_path)
        if pair.clusters_json_path
        else bundle.layout.compare_pair_dir(pair.id) / compare_dxf_mod.CLUSTERS_JSON_NAME
    )
    if not path.is_file():
        return [_cluster_dict(row) for row in rows]
    payload = json.loads(path.read_text(encoding="utf-8"))
    merged = compare_dxf_mod.merge_decisions(payload, rows)
    return list(merged.get("clusters") or [])


def _plan(bundle: BundleHandle, compare_set_id: str) -> list[_SheetPlan]:
    """Every exportable 도곽 짝, in sheet order."""
    with bundle.session_factory() as session:
        pairs = repos.list_pairs(session, compare_set_id)
        frames = {row.id: row for row in repos.list_frames(session, compare_set_id)}
        files = {
            frame.file_id: repos.get_drawing_file(session, frame.file_id)
            for frame in frames.values()
        }

    plans: list[_SheetPlan] = []
    for pair in sorted(pairs, key=lambda row: (row.sort_key, row.id)):
        if pair.status in UNEXPORTABLE_PAIR_STATUSES:
            continue
        frame = frames.get(pair.after_frame_id or "")
        if frame is None:
            continue
        drawing_file = files.get(frame.file_id)
        if drawing_file is None or not drawing_file.working_dxf_path:
            continue
        clusters = _pair_clusters(bundle, pair)
        if not clusters:
            continue
        fallback = Path(drawing_file.original_name or "").stem or pair.sort_key
        plans.append(
            _SheetPlan(
                pair=pair,
                frame=frame,
                frame_record=_frame_record(frame),
                working_dxf=Path(drawing_file.working_dxf_path),
                sheet_no=frame.sheet_no or fallback,
                sheet_title=frame.sheet_title or "",
                clusters=clusters,
            )
        )
    return plans


def change_list_rows(plans: list[_SheetPlan], run_date: str) -> list[ChangeListRow]:
    """Every decided cluster of every sheet, in sheet order then number order."""
    rows: list[ChangeListRow] = []
    for plan in plans:
        for cluster in plan.decided:
            rows.append(
                ChangeListRow(
                    sheet_no=plan.sheet_no,
                    sheet_title=plan.sheet_title,
                    number=int(cluster["number"]),
                    kind=str(cluster.get("kind") or ""),
                    content=markup_mod.cluster_content(cluster),
                    decision=str(cluster.get("decision") or ""),
                    run_date=run_date,
                )
            )
    return rows


# --------------------------------------------------------------------------- the job


def open_run(
    bundle: BundleHandle,
    *,
    compare_set_id: str,
    run_date: str,
    scope: str = "all",
    method: str = "auto",
    config: CompareConfig | None = None,
) -> RunRow:
    """Reserve the output folder and open the ``run`` row (contract §3).

    Called by the router *before* the job starts, because ``POST .../export``
    answers with ``run_id`` (contract §7) and because creating the folder is
    what makes the ``-2`` suffix reliable: two exports started in the same
    second must not both decide they are the first one of the day.
    """
    settings = config or load_compare_config(bundle)
    project_dir = bundle.layout.root.parent
    output_dir, layer_name = resolve_output_dir(project_dir, run_date, settings)
    output_dir.mkdir(parents=True, exist_ok=True)
    with bundle.session_factory() as session:
        return repos.create_run(
            session,
            compare_set_id=compare_set_id,
            run_date=run_date,
            layer_name=layer_name,
            output_dir=str(output_dir),
            scope=scope,
            method=effective_method(method, settings),
            status="running",
        )


async def run_export(
    app: Any,
    *,
    job: jobs_mod.JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    run_date: str,
    scope: str = "all",
    method: str = "auto",
    run_id: str | None = None,
    zwcad_com: zwcad.ComBackend | None = None,
) -> RunRow:
    """The ``compare.export`` job body (contract §6, §7).

    ``run_id`` is the row :func:`open_run` already created for the 202 response;
    a direct caller (a test, the CLI) may leave it out and let this open its
    own. ``zwcad_com`` is the same test-only COM seam
    ``compare/ingest_set.py`` uses -- production never passes it.
    """
    config = load_compare_config(bundle)
    if run_id is None:
        run = open_run(
            bundle,
            compare_set_id=compare_set_id,
            run_date=run_date,
            scope=scope,
            method=method,
            config=config,
        )
        run_id = run.id

    async def _work(reporter: jobs_mod.ProgressReporter) -> None:
        await _do_export(
            app,
            job=job,
            bundle=bundle,
            compare_set_id=compare_set_id,
            run_id=run_id,
            config=config,
            reporter=reporter,
            zwcad_com=zwcad_com,
        )

    await jobs_mod.run_job(app, job, _work)

    with bundle.session_factory() as session:
        row = repos.get_run(session, run_id)
        if row is None:  # pragma: no cover - the row was just created
            raise KeyError(f"run {run_id!r} not found")
        session.expunge(row)
        return row


async def _do_export(
    app: Any,
    *,
    job: jobs_mod.JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    run_id: str,
    config: CompareConfig,
    reporter: jobs_mod.ProgressReporter,
    zwcad_com: zwcad.ComBackend | None,
) -> None:
    loop = asyncio.get_running_loop()
    job_manager = jobs_mod.get_job_manager(app)

    with bundle.session_factory() as session:
        run = repos.get_run(session, run_id)
        if run is None:
            raise KeyError(f"run {run_id!r} not found")
        output_dir = Path(run.output_dir)
        layer_name = run.layer_name
        run_date = run.run_date
        method = run.method

    roots = [bundle.layout.root, output_dir]
    plans = _plan(bundle, compare_set_id)
    exportable = [plan for plan in plans if plan.approved]

    zwcad_status = zwcad.detect()
    acad_bridge_bin = resolve_acad_bridge_bin(getattr(app.state, "settings", None))
    writer, warnings = choose_writer(
        method, zwcad_available=zwcad_status.available, acad_bridge_bin=acad_bridge_bin
    )

    with bundle.session_factory() as session:
        repos.update_compare_set(session, compare_set_id, status="exporting")

    files: list[dict[str, Any]] = []
    pair_ids: list[str] = []
    failures: list[dict[str, str]] = []
    used_names: set[str] = set()
    zwcad_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="halo-zwcad-export")
    converter: zwcad.ZwcadConverter | None = None
    total_steps = max(len(exportable) * 2, 1)
    step = 0

    with bundle.session_factory() as session:
        compare_set = repos.get_compare_set(session, compare_set_id)
        after_set = (
            repos.get_drawing_set(session, compare_set.after_set_id)
            if compare_set is not None
            else None
        )
    after_label = (after_set.label if after_set is not None else None) or "after"

    try:
        for plan in exportable:
            current = job_manager.get(job.id)
            if current is not None and current.cancel_requested:
                raise jobs_mod.JobCancelled

            task = MarkupTask(
                pair_id=plan.pair.id,
                sheet_no=plan.frame.sheet_no,
                after_working_dxf=str(plan.working_dxf),
                frame=plan.frame_record,
                clusters=plan.clusters,
                run_date=run_date,
                layer_name=layer_name,
                out_path=str(
                    bundle.layout.compare_pair_dir(plan.pair.id) / markup_mod.MARKUP_DXF_NAME
                ),
                bundle_root=str(bundle.layout.root),
            )
            result: MarkupPairOutput = await loop.run_in_executor(
                job_manager.executor, markup_pair, task, config
            )
            step += 1
            await reporter(
                step / total_steps,
                f"markup {len(files) + 1}/{len(exportable)} {plan.sheet_no}",
                stage="markup",
                extra={"pair_id": plan.pair.id, "sheet_no": plan.sheet_no, "writer": writer},
            )
            if result.error or result.path is None:
                failures.append(
                    {"pair_id": plan.pair.id, "error": result.error or "no markup written"}
                )
                warnings.extend(result.warnings)
                step += 1
                continue
            warnings.extend(result.warnings)

            stem = markup_file_stem(config, sheet_no=plan.sheet_no, after_label=after_label)
            if stem in used_names:
                warnings.append(WARN_DUPLICATE_FILE_NAME)
                suffix = 2
                while f"{stem}-{suffix}" in used_names:
                    suffix += 1
                stem = f"{stem}-{suffix}"
            used_names.add(stem)

            markup_dxf = Path(result.path)
            file_writer = writer
            out_path = output_dir / f"{stem}.dwg"
            if writer == WRITER_ZWCAD:
                try:
                    if converter is None:
                        converter = await loop.run_in_executor(
                            zwcad_executor,
                            lambda: zwcad.ZwcadConverter(
                                timeout_s=config.ingest.zwcad_timeout_s, com=zwcad_com
                            ),
                        )
                    assert_writable_path(out_path, allowed_roots=roots)
                    await loop.run_in_executor(
                        zwcad_executor, converter.convert_dxf_to_dwg, markup_dxf, out_path
                    )
                except zwcad.ZwcadError as error:
                    logger.warning("ZWCAD could not write %s: %s", out_path, error)
                    warnings.append(WARN_ZWCAD_FAILED)
                    file_writer = WRITER_DXF_ONLY
                    out_path = copy_as_dxf(
                        markup_dxf, output_dir / f"{stem}.dxf", allowed_roots=roots
                    )
            elif writer == WRITER_ACAD_TS and acad_bridge_bin is not None:
                try:
                    # A subprocess, so a plain thread rather than the CPU pool:
                    # this task waits on Node, it does not compute.
                    await asyncio.to_thread(
                        convert_with_acad_ts,
                        acad_bridge_bin,
                        markup_dxf,
                        out_path,
                        allowed_roots=roots,
                    )
                except Exception as error:  # noqa: BLE001 - falls back to a DXF
                    logger.warning("acad-ts could not write %s: %s", out_path, error)
                    warnings.append(WARN_ACAD_TS_FAILED)
                    file_writer = WRITER_DXF_ONLY
                    out_path = copy_as_dxf(
                        markup_dxf, output_dir / f"{stem}.dxf", allowed_roots=roots
                    )
            else:
                out_path = copy_as_dxf(markup_dxf, output_dir / f"{stem}.dxf", allowed_roots=roots)

            files.append(
                {
                    "pair_id": plan.pair.id,
                    "sheet_no": plan.frame.sheet_no,
                    "path": str(out_path),
                    "format": "dwg" if out_path.suffix.lower() == ".dwg" else "dxf",
                    "writer": file_writer,
                }
            )
            pair_ids.append(plan.pair.id)
            step += 1
            await reporter(
                step / total_steps,
                f"dwg {len(files)}/{len(exportable)} {plan.sheet_no}",
                stage="dwg",
                extra={
                    "pair_id": plan.pair.id,
                    "sheet_no": plan.sheet_no,
                    "writer": file_writer,
                },
            )
    finally:
        if converter is not None:
            await loop.run_in_executor(zwcad_executor, converter.__exit__, None, None, None)
        zwcad_executor.shutdown(wait=True)

    rows = change_list_rows(plans, run_date)
    approved_count = sum(len(plan.approved) for plan in plans)
    ignored_count = sum(1 for row in rows if row.decision == "ignored")
    write_changes_tsv(rows, output_dir / CHANGES_TSV_NAME, allowed_roots=roots)

    with bundle.session_factory() as session:
        run = repos.update_run(
            session,
            run_id,
            pair_ids=pair_ids,
            approved_count=approved_count,
            ignored_count=ignored_count,
            files=files,
            status="done",
            error_message=None,
        )
        write_run_json(run, output_dir / RUN_JSON_NAME, allowed_roots=roots)

        compare_set = repos.get_compare_set(session, compare_set_id)
        stats: dict[str, Any] = dict((compare_set.stats if compare_set is not None else None) or {})
        stats.update(
            {
                "last_job_id": job.id,
                "export": {
                    "run_id": run_id,
                    "output_dir": str(output_dir),
                    "layer_name": layer_name,
                    "method": method,
                    "writer": writer,
                    "files": len(files),
                    "approved": approved_count,
                    "ignored": ignored_count,
                    "sheets_skipped": len(plans) - len(exportable),
                    "warnings": sorted(set(warnings)),
                    "failed": failures,
                },
            }
        )
        repos.update_compare_set(session, compare_set_id, status="compared", stats=stats)


__all__ = [
    "ACAD_TS_TIMEOUT_S",
    "CHANGES_TSV_NAME",
    "DECISION_LABELS",
    "KIND_LABELS",
    "RUN_JSON_NAME",
    "SCHEMA_VERSION",
    "TSV_COLUMNS",
    "UNEXPORTABLE_PAIR_STATUSES",
    "WARN_ACAD_TS_FAILED",
    "WARN_ACAD_TS_TITLEBLOCK",
    "WARN_ACAD_TS_UNAVAILABLE",
    "WARN_DUPLICATE_FILE_NAME",
    "WARN_ZWCAD_FAILED",
    "WARN_ZWCAD_UNAVAILABLE",
    "WRITER_ACAD_TS",
    "WRITER_DXF_ONLY",
    "WRITER_ZWCAD",
    "ChangeListRow",
    "MarkupPairOutput",
    "MarkupTask",
    "change_list_rows",
    "choose_writer",
    "convert_with_acad_ts",
    "copy_as_dxf",
    "effective_method",
    "markup_file_stem",
    "markup_pair",
    "open_run",
    "resolve_acad_bridge_bin",
    "resolve_output_dir",
    "run_export",
    "run_payload",
    "sanitize_file_name",
    "write_changes_tsv",
    "write_run_json",
]
