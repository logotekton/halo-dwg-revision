"""F01-F10: the engine's ``halo_engine.ingest.stats`` and the fixture
generator's ``fixtures_gen.stats`` (an intentionally independent
implementation, brief Constraints: "서로 임포트하지 않는다") must compute the
same statistics for the same DXF bytes.

This compares the engine's live computation against the already-committed
``fixtures/truth/F##.json`` (produced by ``fixtures_gen.stats`` when the
fixtures were generated -- see ``fixtures/gen/src/fixtures_gen/pipeline.py``)
rather than importing ``fixtures_gen`` here: the two are independent uv
projects (root ``pyproject.toml`` excludes ``fixtures/gen`` from the engine's
workspace on purpose), and comparing against the committed truth is exactly
what the brief's acceptance flow does.

``producer`` is excluded from the comparison: it correctly differs (one
document was produced by ``halo-engine stats`` in-process, the other by the
fixture generator's independent reader; see the W2-03 report's Decisions
for why both use the ``"engine.ezdxf"`` producer name with a distinguishing
version) -- "byte identical" here means the actually measured content
(``schema_version``, ``file_sha256``, ``buckets``, ``totals``), compared as
sorted-key JSON per the brief.
"""

from __future__ import annotations

import hashlib
import json

import ezdxf
import pytest
from conftest import FIXTURES_GENERATED, FIXTURES_TRUTH

from halo_engine.ingest.stats import compute_layer_stats

COMPARABLE_KEYS = ("schema_version", "file_sha256", "buckets", "totals")

#: (truth file, dxf file) pairs for F01-F10.
_CASES: list[tuple[str, str]] = [(f"F{i:02d}.json", f"F{i:02d}.dxf") for i in range(1, 10)]
_CASES += [("F10_grid.json", "F10_grid.dxf"), ("F10_host.json", "F10_host.dxf")]


def _comparable(doc: dict) -> str:
    return json.dumps({k: doc[k] for k in COMPARABLE_KEYS}, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("truth_name,dxf_name", _CASES, ids=[c[1] for c in _CASES])
def test_engine_stats_match_fixtures_gen_truth(truth_name: str, dxf_name: str) -> None:
    truth_path = FIXTURES_TRUTH / truth_name
    dxf_path = FIXTURES_GENERATED / dxf_name
    if not (truth_path.exists() and dxf_path.exists()):
        pytest.skip(f"{truth_path} or {dxf_path} not generated yet")

    truth_doc = json.loads(truth_path.read_text(encoding="utf-8"))

    doc = ezdxf.readfile(str(dxf_path))
    file_sha256 = hashlib.sha256(dxf_path.read_bytes()).hexdigest()
    engine_doc = compute_layer_stats(doc, file_sha256=file_sha256)

    assert _comparable(engine_doc) == _comparable(truth_doc)
