"""Fixtures shared by every ``tests/compare`` module.

A comparison always starts from an open bundle: the settings are read out of it,
the compare DXF and the sidecar are written into it, and the export writes next
to it. So the fixture here is a real bundle on a temp path -- migrated, with its
directories made -- rather than a mock. It is cheap (an empty SQLite file and a
handful of ``mkdir``s) and it means a test that gets the paths wrong fails here
instead of on Windows.

Later R1 tasks reuse these: ``compare_bundle`` for anything that needs paths or
the database, ``compare_layout`` when only the paths matter, ``compare_session``
for the repos round trips, and ``project_dir`` for the output folder, which sits
next to the bundle rather than inside it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from halo_engine.bundle.create import BundleHandle, create_bundle
from halo_engine.bundle.layout import BundleLayout

#: The date every compare fixture runs on. Pinned, because `run_date` is an
#: explicit input and nothing in the engine may reach for today's date
#: (``docs/contracts/r1.md`` §11).
RUN_DATE = "2026-09-04"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """The folder the user picked: the bundle's parent, and where 출력/ goes."""
    root = tmp_path / "한강자이"
    root.mkdir()
    return root


@pytest.fixture
def compare_bundle(project_dir: Path) -> BundleHandle:
    """An open bundle at ``<project_dir>/.halo``, migrated to head."""
    return create_bundle(project_dir / ".halo", project_dir.name)


@pytest.fixture
def compare_layout(compare_bundle: BundleHandle) -> BundleLayout:
    return compare_bundle.layout


@pytest.fixture
def compare_session(compare_bundle: BundleHandle) -> Iterator[Session]:
    """A session on the bundle's own database, closed at the end of the test."""
    with compare_bundle.session_factory() as session:
        yield session
