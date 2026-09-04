"""The R1 comparison tables: migration, repos round trips, and carried-over decisions.

Lives next to ``test_db.py`` for the same reason that one does -- a bundle is
what stands the database up, and ``create_bundle`` is what runs the migration.

The migration is exercised from both directions a real machine can be in: a
bundle created today (where ``0001_initial`` already built every table from live
``Base.metadata``) and a bundle that stopped at ``0002`` before this task landed.
Both have to reach the same schema, which is the whole reason ``0003`` guards
every statement with an existence check.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command

from halo_engine.bundle.create import BundleHandle, create_bundle, open_bundle
from halo_engine.bundle.layout import BundleLayout
from halo_engine.db import repos

# Private, on purpose: the test needs the same Alembic Config the engine builds,
# and duplicating it here would let the two drift.
from halo_engine.db.migrate import _config_for, upgrade_to_head

COMPARE_TABLES = {"compare_set", "sheet_frame", "sheet_pair", "change", "cluster", "run"}
RUN_DATE = "2026-09-04"


def _bundle(tmp_path: Path) -> BundleHandle:
    return create_bundle(tmp_path / "demo.halo", "demo")


def _inspector(sqlite_path: Path) -> sa.Inspector:
    return sa.inspect(sa.create_engine(f"sqlite:///{sqlite_path}"))


class TestMigration:
    def test_a_fresh_bundle_has_every_compare_table(self, tmp_path: Path) -> None:
        handle = _bundle(tmp_path)
        tables = set(_inspector(handle.layout.project_sqlite).get_table_names())
        assert COMPARE_TABLES <= tables

    def test_a_fresh_bundle_has_the_new_file_family_columns(self, tmp_path: Path) -> None:
        handle = _bundle(tmp_path)
        inspector = _inspector(handle.layout.project_sqlite)
        drawing_set = {column["name"] for column in inspector.get_columns("drawing_set")}
        drawing_file = {column["name"] for column in inspector.get_columns("drawing_file")}
        assert {"role", "source_dir"} <= drawing_set
        assert {"converter_meta", "excluded_reason", "font_names"} <= drawing_file

    def test_a_bundle_that_stopped_at_0002_upgrades_to_head(self, tmp_path: Path) -> None:
        sqlite_path = tmp_path / "old.halo" / "project.sqlite"
        sqlite_path.parent.mkdir(parents=True)
        command.upgrade(_config_for(sqlite_path), "0002")

        upgrade_to_head(sqlite_path)

        inspector = _inspector(sqlite_path)
        assert COMPARE_TABLES <= set(inspector.get_table_names())
        version = inspector.get_columns("alembic_version")
        assert version  # the table exists; the value is checked below
        with sa.create_engine(f"sqlite:///{sqlite_path}").connect() as connection:
            head = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert head == "0003_compare_records"

    def test_upgrade_is_idempotent(self, tmp_path: Path) -> None:
        handle = _bundle(tmp_path)
        # open_bundle migrates again; running 0003 twice must not fail.
        reopened = open_bundle(handle.layout.root)
        assert reopened.id == handle.id
        upgrade_to_head(handle.layout.project_sqlite)

    def test_downgrade_removes_the_compare_schema_and_upgrade_restores_it(
        self, tmp_path: Path
    ) -> None:
        handle = _bundle(tmp_path)
        sqlite_path = handle.layout.project_sqlite
        handle.engine.dispose()
        config = _config_for(sqlite_path)

        command.downgrade(config, "0002")
        inspector = _inspector(sqlite_path)
        assert not (COMPARE_TABLES & set(inspector.get_table_names()))
        assert "role" not in {c["name"] for c in inspector.get_columns("drawing_set")}

        command.upgrade(config, "head")
        inspector = _inspector(sqlite_path)
        assert COMPARE_TABLES <= set(inspector.get_table_names())
        assert "role" in {c["name"] for c in inspector.get_columns("drawing_set")}


class TestBundleLayout:
    def test_the_compare_paths_hang_off_the_bundle_root(self, tmp_path: Path) -> None:
        root = tmp_path / "한강자이" / ".halo"
        layout = BundleLayout(root)
        assert layout.compare_dir == root / "compare"
        assert layout.log_dir == root / "log"
        assert layout.compare_yaml == root / "compare.yaml"
        assert layout.frames_yaml == root / "frames.yaml"
        assert (
            layout.compare_pair_dir("01JQ8Z5K3M7P0RSTVWXYZ0A1BA")
            == root / "compare" / "01JQ8Z5K3M7P0RSTVWXYZ0A1BA"
        )

    def test_ensure_dirs_makes_compare_and_log(self, tmp_path: Path) -> None:
        layout = BundleLayout(tmp_path / "demo.halo")
        layout.ensure_dirs()
        assert layout.compare_dir.is_dir()
        assert layout.log_dir.is_dir()

    @pytest.mark.parametrize("pair_id", ["..", "../../etc", "a/b", "", "not-a-ulid"])
    def test_a_pair_id_that_is_not_a_ulid_never_becomes_a_path(
        self, tmp_path: Path, pair_id: str
    ) -> None:
        layout = BundleLayout(tmp_path / "demo.halo")
        with pytest.raises(ValueError):
            layout.compare_pair_dir(pair_id)


@pytest.fixture
def seeded(tmp_path: Path) -> tuple[BundleHandle, dict[str, str]]:
    """A bundle with two sets, one file per side, and a compare set over them."""
    handle = _bundle(tmp_path)
    with handle.session_factory() as session:
        before_set = repos.create_drawing_set(session, project_id=handle.id, label="20260702")
        after_set = repos.create_drawing_set(session, project_id=handle.id, label="20260820")
        before_file = repos.create_drawing_file(
            session,
            drawing_set_id=before_set.id,
            original_path="/abs/before/A-101.dwg",
            original_name="A-101.dwg",
            sha256="a" * 64,
            format="DWG",
            import_status="DONE",
        )
        after_file = repos.create_drawing_file(
            session,
            drawing_set_id=after_set.id,
            original_path="/abs/after/A-101.dwg",
            original_name="A-101.dwg",
            sha256="b" * 64,
            format="DWG",
            import_status="DONE",
        )
        compare_set = repos.create_compare_set(
            session,
            project_id=handle.id,
            before_set_id=before_set.id,
            after_set_id=after_set.id,
            run_date=RUN_DATE,
        )
        ids = {
            "before_set": before_set.id,
            "after_set": after_set.id,
            "before_file": before_file.id,
            "after_file": after_file.id,
            "compare_set": compare_set.id,
        }
    return handle, ids


def _frame(file_id: str, *, sheet_no: str, sort_index: int = 0) -> dict[str, object]:
    return {
        "file_id": file_id,
        "kind": "titleblock",
        "titleblock_handle": "1F3",
        "block_name": "TITLE_A1",
        "bbox": [0.0, 0.0, 84100.0, 59400.0],
        "sheet_no": sheet_no,
        "sheet_title": "3층 평면도",
        "scale_text": "1:100",
        "scale_denominator": 100,
        "date_text": "2026-08-20",
        "norm_key": sheet_no,
        "sort_index": sort_index,
        "entity_handles": ["1A3", "1A4"],
        "provenance": {"file": file_id, "handle": "1F3", "path": [], "space": "MODEL"},
        "attributes": {"DWG_NO": sheet_no},
    }


def _change(seq: int, *, minor: bool = False) -> dict[str, object]:
    return {
        "seq": seq,
        "kind": "moved",
        "etype": "INSERT",
        "layer": "A-DOOR",
        "before_handle": f"1A{seq}",
        "after_handle": f"1A{seq}",
        "bbox": [0.0, 0.0, 100.0, 100.0],
        "delta": {"move": [1250.0, 0.0], "distance": 1250.0},
        "minor": minor,
        "minor_reason": "layer_only" if minor else None,
        "provenance": {"after": {"file": "x", "handle": f"1A{seq}", "path": [], "space": "MODEL"}},
    }


def _cluster(number: int, signature: str, *, seqs: list[int]) -> dict[str, object]:
    return {
        "number": number,
        "signature": signature,
        "bbox": [0.0, 0.0, 100.0, 100.0],
        "kind": "moved",
        "label": f"블록 이동 {number}",
        "user_label": None,
        "decision": "pending",
        "note": None,
        "change_seqs": seqs,
        "cloud": {"handle": None, "points": [[0.0, 0.0, 0.5]]},
        "badge": {"shape_handle": None, "text_handle": None, "center": [110.0, 110.0]},
    }


class TestCompareSetRepos:
    def test_create_get_update_list(self, seeded: tuple[BundleHandle, dict[str, str]]) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            row = repos.get_compare_set(session, ids["compare_set"])
            assert row is not None
            assert row.run_date == RUN_DATE
            assert row.status == "ingesting"
            assert row.options == {}

            updated = repos.update_compare_set(
                session, row.id, status="ingested", stats={"fonts_missing": []}
            )
            assert updated.status == "ingested"
            assert updated.stats == {"fonts_missing": []}

            assert [c.id for c in repos.list_compare_sets(session)] == [row.id]
            assert repos.list_compare_sets(session, project_id="nope") == []
            assert repos.get_compare_set(session, "nonexistent") is None

    def test_an_unknown_column_is_refused_instead_of_silently_dropped(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            with pytest.raises(KeyError):
                repos.update_compare_set(session, ids["compare_set"], statuss="ingested")

    def test_updating_something_that_is_not_there_raises(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, _ = seeded
        with handle.session_factory() as session:
            with pytest.raises(KeyError):
                repos.update_compare_set(session, "nonexistent", status="failed")


class TestFramesAndPairs:
    def test_frames_round_trip_and_replace(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            repos.replace_frames(
                session,
                ids["compare_set"],
                "before",
                [_frame(ids["before_file"], sheet_no="A-101")],
            )
            repos.replace_frames(
                session,
                ids["compare_set"],
                "after",
                [
                    _frame(ids["after_file"], sheet_no="A-101"),
                    _frame(ids["after_file"], sheet_no="A-102", sort_index=1),
                ],
            )

            after = repos.list_frames(session, ids["compare_set"], role="after")
            assert [f.sheet_no for f in after] == ["A-101", "A-102"]
            assert after[0].bbox == [0.0, 0.0, 84100.0, 59400.0]
            assert after[0].attributes == {"DWG_NO": "A-101"}
            assert len(repos.list_frames(session, ids["compare_set"])) == 3

            # Replacing one side leaves the other alone.
            repos.replace_frames(
                session,
                ids["compare_set"],
                "after",
                [_frame(ids["after_file"], sheet_no="A-101")],
            )
            assert len(repos.list_frames(session, ids["compare_set"], role="after")) == 1
            assert len(repos.list_frames(session, ids["compare_set"], role="before")) == 1

    def test_pairs_round_trip(self, seeded: tuple[BundleHandle, dict[str, str]]) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            before = repos.replace_frames(
                session,
                ids["compare_set"],
                "before",
                [_frame(ids["before_file"], sheet_no="A-101")],
            )
            after = repos.replace_frames(
                session, ids["compare_set"], "after", [_frame(ids["after_file"], sheet_no="A-101")]
            )
            pairs = repos.replace_pairs(
                session,
                ids["compare_set"],
                [
                    {
                        "before_frame_id": before[0].id,
                        "after_frame_id": after[0].id,
                        "status": "pending",
                        "match_method": "number",
                        "score": 1.0,
                        "sort_key": "A-101",
                    }
                ],
            )
            assert len(pairs) == 1
            pair = repos.get_pair(session, pairs[0].id)
            assert pair is not None
            assert pair.match_method == "number"
            assert pair.change_count == 0

            updated = repos.update_pair(
                session, pair.id, status="changed", warnings=["offset_only"]
            )
            assert updated.status == "changed"
            assert updated.warnings == ["offset_only"]

            assert [p.id for p in repos.list_pairs(session, ids["compare_set"])] == [pair.id]
            assert repos.list_pairs(session, ids["compare_set"], status="same") == []

    def test_re_extracting_frames_clears_the_pairs_they_belonged_to(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            before = repos.replace_frames(
                session,
                ids["compare_set"],
                "before",
                [_frame(ids["before_file"], sheet_no="A-101")],
            )
            after = repos.replace_frames(
                session, ids["compare_set"], "after", [_frame(ids["after_file"], sheet_no="A-101")]
            )
            repos.replace_pairs(
                session,
                ids["compare_set"],
                [
                    {
                        "before_frame_id": before[0].id,
                        "after_frame_id": after[0].id,
                        "status": "pending",
                        "sort_key": "A-101",
                    }
                ],
            )
            assert repos.list_pairs(session, ids["compare_set"])

            repos.replace_frames(
                session, ids["compare_set"], "after", [_frame(ids["after_file"], sheet_no="A-101")]
            )
            assert repos.list_pairs(session, ids["compare_set"]) == []

    def test_a_manual_pair_replaces_whatever_the_two_frames_were_in(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            before = repos.replace_frames(
                session,
                ids["compare_set"],
                "before",
                [_frame(ids["before_file"], sheet_no="A-101")],
            )
            after = repos.replace_frames(
                session, ids["compare_set"], "after", [_frame(ids["after_file"], sheet_no="A-1O1")]
            )
            # The matcher could not pair them: two one-sided rows.
            repos.replace_pairs(
                session,
                ids["compare_set"],
                [
                    {"before_frame_id": before[0].id, "status": "removed", "sort_key": "A-101"},
                    {"after_frame_id": after[0].id, "status": "added", "sort_key": "A-1O1"},
                ],
            )
            assert len(repos.list_pairs(session, ids["compare_set"])) == 2

            manual = repos.create_manual_pair(
                session,
                compare_set_id=ids["compare_set"],
                before_frame_id=before[0].id,
                after_frame_id=after[0].id,
            )
            assert manual.match_method == "manual"
            assert manual.status == "pending"
            assert manual.sort_key == "A-1O1"
            assert [p.id for p in repos.list_pairs(session, ids["compare_set"])] == [manual.id]

            repos.delete_pair(session, manual.id)
            assert repos.list_pairs(session, ids["compare_set"]) == []

    def test_only_a_manual_pair_can_be_deleted(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            pairs = repos.replace_pairs(
                session,
                ids["compare_set"],
                [{"status": "added", "match_method": "number", "sort_key": "A-101"}],
            )
            with pytest.raises(ValueError):
                repos.delete_pair(session, pairs[0].id)
            repos.delete_pair(session, pairs[0].id, manual_only=False)
            assert repos.list_pairs(session, ids["compare_set"]) == []


@pytest.fixture
def pair_id(seeded: tuple[BundleHandle, dict[str, str]]) -> tuple[BundleHandle, str]:
    handle, ids = seeded
    with handle.session_factory() as session:
        pairs = repos.replace_pairs(
            session,
            ids["compare_set"],
            [{"status": "pending", "match_method": "number", "sort_key": "A-101"}],
        )
        return handle, pairs[0].id


class TestChangesAndClusters:
    def test_changes_round_trip_and_refresh_the_pair_counts(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            rows = repos.replace_changes(
                session, pid, [_change(1), _change(2, minor=True), _change(3)]
            )
            assert [r.seq for r in rows] == [1, 2, 3]
            assert repos.list_changes(session, pid)[1].minor_reason == "layer_only"

            pair = repos.get_pair(session, pid)
            assert pair is not None
            assert (pair.change_count, pair.minor_count) == (3, 1)

            repos.replace_changes(session, pid, [_change(1)])
            assert len(repos.list_changes(session, pid)) == 1
            pair = repos.get_pair(session, pid)
            assert pair is not None
            assert (pair.change_count, pair.minor_count) == (1, 0)

    def test_clusters_round_trip_and_are_addressed_by_number(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            repos.replace_clusters(
                session,
                pid,
                [_cluster(1, "sig-a", seqs=[1]), _cluster(2, "sig-b", seqs=[2, 3])],
            )
            clusters = repos.list_clusters(session, pid)
            assert [c.number for c in clusters] == [1, 2]
            assert clusters[1].change_seqs == [2, 3]
            assert clusters[0].decision == "pending"

            pair = repos.get_pair(session, pid)
            assert pair is not None
            assert pair.cluster_count == 2

            assert repos.get_cluster_by_number(session, pid, 2) is not None
            assert repos.get_cluster_by_number(session, pid, 7) is None

            decided = repos.update_cluster(
                session, pid, 1, decision="approved", user_label="문 이동", note="현장 확인"
            )
            assert (decided.decision, decided.user_label, decided.note) == (
                "approved",
                "문 이동",
                "현장 확인",
            )

            # A PATCH that clears the memo sends `note: null`.
            cleared = repos.update_cluster(session, pid, 1, note=None)
            assert cleared.note is None
            assert cleared.decision == "approved"

            with pytest.raises(KeyError):
                repos.update_cluster(session, pid, 9, decision="ignored")

    def test_a_re_run_carries_the_users_review_over_by_signature(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            repos.replace_clusters(
                session, pid, [_cluster(1, "sig-a", seqs=[1]), _cluster(2, "sig-b", seqs=[2])]
            )
            repos.update_cluster(
                session, pid, 1, decision="approved", user_label="문 이동", note="확인함"
            )
            repos.update_cluster(session, pid, 2, decision="ignored")

            # The comparison runs again: new rows, new numbers, same underlying
            # changes for `sig-a`, and one cluster that was not there before.
            repos.replace_clusters(
                session,
                pid,
                [
                    _cluster(1, "sig-c", seqs=[5]),
                    _cluster(2, "sig-a", seqs=[1]),
                    _cluster(3, "sig-b", seqs=[2]),
                ],
            )
            by_signature = {c.signature: c for c in repos.list_clusters(session, pid)}

            carried = by_signature["sig-a"]
            assert carried.number == 2  # renumbered ...
            assert carried.decision == "approved"  # ... but the review survived
            assert carried.user_label == "문 이동"
            assert carried.note == "확인함"

            assert by_signature["sig-b"].decision == "ignored"
            assert by_signature["sig-c"].decision == "pending"
            assert by_signature["sig-c"].user_label is None

    def test_keep_decisions_false_starts_the_review_over(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            repos.replace_clusters(session, pid, [_cluster(1, "sig-a", seqs=[1])])
            repos.update_cluster(session, pid, 1, decision="approved", user_label="문 이동")

            repos.replace_clusters(
                session, pid, [_cluster(1, "sig-a", seqs=[1])], keep_decisions=False
            )
            fresh = repos.list_clusters(session, pid)[0]
            assert fresh.decision == "pending"
            assert fresh.user_label is None

    def test_an_incoming_decision_wins_over_the_carried_one(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            repos.replace_clusters(session, pid, [_cluster(1, "sig-a", seqs=[1])])
            repos.update_cluster(session, pid, 1, decision="ignored")

            incoming = _cluster(1, "sig-a", seqs=[1])
            incoming["decision"] = "approved"
            repos.replace_clusters(session, pid, [incoming])
            assert repos.list_clusters(session, pid)[0].decision == "approved"

    def test_deleting_a_pair_takes_its_changes_and_clusters_with_it(
        self, pair_id: tuple[BundleHandle, str]
    ) -> None:
        handle, pid = pair_id
        with handle.session_factory() as session:
            repos.replace_changes(session, pid, [_change(1)])
            repos.replace_clusters(session, pid, [_cluster(1, "sig-a", seqs=[1])])

            repos.delete_pair(session, pid, manual_only=False)

            assert repos.get_pair(session, pid) is None
            assert repos.list_changes(session, pid) == []
            assert repos.list_clusters(session, pid) == []


class TestRuns:
    def test_run_round_trip(self, seeded: tuple[BundleHandle, dict[str, str]]) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            run = repos.create_run(
                session,
                compare_set_id=ids["compare_set"],
                run_date=RUN_DATE,
                layer_name="REV-20260904",
                output_dir="/abs/한강자이/출력/2026-09-04",
                method="auto",
                pair_ids=["01JQ8Z5K3M7P0RSTVWXYZ0A1BA"],
                approved_count=3,
            )
            assert run.status == "running"
            assert run.scope == "all"
            assert run.files == []

            done = repos.update_run(
                session,
                run.id,
                status="done",
                files=[
                    {
                        "pair_id": "01JQ8Z5K3M7P0RSTVWXYZ0A1BA",
                        "sheet_no": "A-101",
                        "path": "/abs/out/A-101_20260820_markup.dwg",
                        "format": "dwg",
                        "writer": "zwcad-com",
                    }
                ],
            )
            assert done.status == "done"
            assert done.files[0]["writer"] == "zwcad-com"

            assert repos.get_run(session, run.id) is not None
            assert [r.id for r in repos.list_runs(session, ids["compare_set"])] == [run.id]
            assert repos.get_run(session, "nonexistent") is None

    def test_a_second_run_of_the_same_day_is_listed_first(
        self, seeded: tuple[BundleHandle, dict[str, str]]
    ) -> None:
        handle, ids = seeded
        with handle.session_factory() as session:
            first = repos.create_run(
                session,
                compare_set_id=ids["compare_set"],
                run_date=RUN_DATE,
                layer_name="REV-20260904",
                output_dir="/abs/out/2026-09-04",
                method="auto",
            )
            second = repos.create_run(
                session,
                compare_set_id=ids["compare_set"],
                run_date=RUN_DATE,
                layer_name="REV-20260904-2",
                output_dir="/abs/out/2026-09-04-2",
                method="auto",
            )
            listed = [r.id for r in repos.list_runs(session, ids["compare_set"])]
            assert listed[0] == second.id
            assert set(listed) == {first.id, second.id}
