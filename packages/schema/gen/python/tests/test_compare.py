"""The R1 comparison contract, checked on the Python side.

The engine writes `clusters.json` and `run.json` and answers every
`/api/v1/compare/...` request, so it is the producer of seven of these eight
documents and the consumer of the eighth (`compare/truth.schema.json`, written
by the fixture generator). Whatever ajv refuses in the viewer has to be refused
here too, which is what these tests pin: the same example files, the same
verdicts, plus the cross-reference rule that JSON Schema cannot express.
"""

from __future__ import annotations

from typing import Any

import pytest

from halo_schema import SCHEMA_FILES, SCHEMA_VERSION
from halo_schema.validation import assert_valid, failures, is_valid

from conftest import load_example

#: Every `compare.*.json` example and the schema key it belongs to. Mirrors the
#: table in `packages/schema/test/examples.test.ts`; the two must not drift.
EXPECTATIONS = [
    ("compare.sheet-frame.json", "compare_sheet_frame", True),
    ("compare.sheet-pair.json", "compare_sheet_pair", True),
    ("compare.change.json", "compare_change", True),
    ("compare.cluster.json", "compare_cluster", True),
    ("compare.run.json", "compare_run", True),
    ("compare.clusters-sidecar.json", "compare_clusters_sidecar", True),
    ("compare.compare-set.json", "compare_set_summary", True),
    ("compare.truth.json", "compare_truth", True),
    ("compare.bad-change-no-provenance.json", "compare_change", False),
    ("compare.bad-change-unknown-kind.json", "compare_change", False),
    ("compare.bad-cluster-decision-typo.json", "compare_cluster", False),
    # Schema-valid on purpose: the dangling reference is a cross-reference the
    # 2020-12 dialect cannot state. `test_dangling_handle_...` below is the check.
    ("compare.bad-sidecar-dangling-handle.json", "compare_clusters_sidecar", True),
]

COMPARE_KEYS = [
    "compare_sheet_frame",
    "compare_sheet_pair",
    "compare_change",
    "compare_cluster",
    "compare_run",
    "compare_clusters_sidecar",
    "compare_set_summary",
    "compare_truth",
]


@pytest.mark.parametrize(("name", "key", "expected"), EXPECTATIONS)
def test_example_matches_expectation(name: str, key: str, expected: bool) -> None:
    document = load_example(name)
    assert is_valid(key, document) is expected, failures(key, document)


def test_every_compare_example_is_covered(examples_dir) -> None:
    on_disk = sorted(path.name for path in examples_dir.glob("compare.*.json"))
    assert on_disk == sorted(name for name, _, _ in EXPECTATIONS)


def test_all_eight_compare_schemas_are_registered() -> None:
    assert [key for key in SCHEMA_FILES if key.startswith("compare_")] == COMPARE_KEYS


def test_documents_written_to_disk_carry_the_schema_version() -> None:
    # clusters.json, run.json and truth.json are files; the API responses are not.
    for name in ("compare.clusters-sidecar.json", "compare.run.json", "compare.truth.json"):
        assert load_example(name)["schema_version"] == SCHEMA_VERSION


def _sidecar() -> dict[str, Any]:
    return load_example("compare.clusters-sidecar.json")


def test_the_compare_dxf_layer_never_carries_the_export_suffix() -> None:
    # `REV-<date>-2` belongs to the second export of a day (R1-09), never to the
    # compare DXF the viewer renders (docs/contracts/compare-dxf.md §2).
    sidecar = _sidecar()
    sidecar["layer"] = "REV-20260904-2"
    assert not is_valid("compare_clusters_sidecar", sidecar)
    run = load_example("compare.run.json")
    run["layer_name"] = "REV-20260904-2"
    assert is_valid("compare_run", run), failures("compare_run", run)


def test_run_date_must_be_an_iso_date() -> None:
    for bad in ("2026-9-4", "20260904", "2026-13-01", "오늘"):
        sidecar = _sidecar()
        sidecar["run_date"] = bad
        assert not is_valid("compare_clusters_sidecar", sidecar), bad


def test_a_change_without_provenance_is_refused_by_name() -> None:
    document = load_example("compare.bad-change-no-provenance.json")
    reasons = failures("compare_change", document)
    assert any("provenance" in reason for reason in reasons), reasons


def test_minor_reasons_join_with_a_plus() -> None:
    change = load_example("compare.change.json")
    change["minor"] = True
    change["minor_reason"] = "layer_only+mtext_format_only"
    assert is_valid("compare_change", change), failures("compare_change", change)
    change["minor_reason"] = "layer_only+almost_the_same"
    assert not is_valid("compare_change", change)


def test_delta_stays_open_for_the_diff_rules_to_fill_in() -> None:
    change = load_example("compare.change.json")
    change["delta"] = {"move": [1250.0, 0.0], "distance": 1250.0, "rotation_deg": 90.0}
    assert is_valid("compare_change", change), failures("compare_change", change)


def test_handle_map_keys_are_dxf_handles() -> None:
    sidecar = _sidecar()
    sidecar["handle_to_cluster"] = {"2f1": "c1"}
    assert not is_valid("compare_clusters_sidecar", sidecar)


def test_dangling_handle_passes_the_schema_and_needs_the_engines_own_check() -> None:
    """The one rule the schema cannot carry.

    `handle_to_cluster` is what turns a click in the viewer into a selected
    cluster. A value naming a cluster that is not in the file is not a type
    error, so the document validates; `compare/compare_dxf.py` (R1-06) asserts
    the reference itself when it writes the pair, exactly as
    `clustersSidecarIntegrityFailures` does on the TypeScript side.
    """
    document = load_example("compare.bad-sidecar-dangling-handle.json")
    assert is_valid("compare_clusters_sidecar", document)
    cluster_ids = {cluster["id"] for cluster in document["clusters"]}
    dangling = sorted(
        handle
        for handle, cluster_id in document["handle_to_cluster"].items()
        if cluster_id not in cluster_ids
    )
    assert dangling == ["2F3"]


def test_assert_valid_names_the_schema_it_used() -> None:
    from halo_schema import SCHEMA_IDS
    from halo_schema.validation import SchemaValidationError

    with pytest.raises(SchemaValidationError) as excinfo:
        assert_valid("compare_cluster", {"id": "c1"}, "clusters.json")
    assert excinfo.value.schema_id == SCHEMA_IDS["compare_cluster"]
    assert excinfo.value.reasons


class TestGeneratedModels:
    """The pydantic models load the same documents the validator accepts."""

    pytestmark = pytest.mark.models

    def test_sidecar_model_round_trips(self) -> None:
        pytest.importorskip("pydantic")
        from halo_schema.models.compare.clusters_sidecar_schema import ClustersSidecar

        original = _sidecar()
        sidecar = ClustersSidecar.model_validate(original)
        assert sidecar.counts.clusters == len(sidecar.clusters)
        assert sidecar.changes[1].minor_reason == "layer_only"
        dumped = sidecar.model_dump(mode="json", exclude_unset=True, by_alias=True)
        # `exclude_unset` reproduces exactly the keys the engine wrote, which is
        # what has to stay byte-identical between two runs.
        assert dumped == original
        assert is_valid("compare_clusters_sidecar", dumped)
        assert dumped["clusters"][0]["change_ids"] == ["ch1"]

    def test_every_compare_model_loads_its_example(self) -> None:
        pytest.importorskip("pydantic")
        from halo_schema.models.compare.change_schema import Change
        from halo_schema.models.compare.cluster_schema import Cluster
        from halo_schema.models.compare.compare_set_schema import CompareSetSummary
        from halo_schema.models.compare.run_schema import Run
        from halo_schema.models.compare.sheet_frame_schema import SheetFrame
        from halo_schema.models.compare.sheet_pair_schema import SheetPair
        from halo_schema.models.compare.truth_schema import RevisionTruth

        assert SheetFrame.model_validate(load_example("compare.sheet-frame.json")).sheet_no == "A-101"
        assert SheetPair.model_validate(load_example("compare.sheet-pair.json")).cluster_count == 1
        assert Change.model_validate(load_example("compare.change.json")).kind.value == "moved"
        assert Cluster.model_validate(load_example("compare.cluster.json")).number == 1
        assert Run.model_validate(load_example("compare.run.json")).status.value == "done"
        summary = CompareSetSummary.model_validate(load_example("compare.compare-set.json"))
        assert summary.zwcad.available is True
        truth = RevisionTruth.model_validate(load_example("compare.truth.json"))
        assert [entry.sheet_no for entry in truth.expected_pairs] == ["A-101", "A-102"]

    def test_a_misspelled_decision_is_refused_by_the_model_too(self) -> None:
        pydantic = pytest.importorskip("pydantic")
        from halo_schema.models.compare.cluster_schema import Cluster

        with pytest.raises(pydantic.ValidationError):
            Cluster.model_validate(load_example("compare.bad-cluster-decision-typo.json"))
