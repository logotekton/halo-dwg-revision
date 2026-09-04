"""Fake ``ComBackend`` for ``compare/zwcad`` tests, reusable by later R1 tasks.

Simulates just enough of the ZWCAD/AutoCAD-style Application COM surface for
``ZwcadConverter`` -- ``Documents.Open``/``SaveAs``/``Close``,
``SetVariable``, ``Visible``, ``HWND``, ``Version``, ``Quit`` -- without
touching real COM. See ``docs/contracts/r1.md`` §6.1 ``ComBackend`` for the
boundary this fakes; attribute names are PascalCase on purpose, to mirror
the real COM automation surface (``ruff`` naming rules are not enabled in
this project).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FakeDocument:
    path: str
    read_only: bool
    saveas_calls: list[tuple[str, int]] = field(default_factory=list)
    close_calls: list[bool] = field(default_factory=list)
    #: override to simulate a slow/hanging SaveAs, or one that raises.
    saveas_hook: Callable[[FakeDocument, str, int], None] | None = None

    def SaveAs(self, path: str, version_constant: int) -> None:  # noqa: N802 - COM method name
        self.saveas_calls.append((path, version_constant))
        if self.saveas_hook is not None:
            self.saveas_hook(self, path, version_constant)
            return
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"FAKE-ZWCAD-OUTPUT\n")

    def Close(self, save_changes: bool) -> None:  # noqa: N802 - COM method name
        self.close_calls.append(save_changes)


@dataclass
class FakeDocuments:
    open_calls: list[tuple[str, bool]] = field(default_factory=list)
    documents: list[FakeDocument] = field(default_factory=list)
    #: override to hand back a custom FakeDocument (e.g. one with a hook).
    open_hook: Callable[[str, bool], FakeDocument] | None = None

    def Open(self, path: str, read_only: bool = False) -> FakeDocument:  # noqa: N802
        self.open_calls.append((path, read_only))
        doc = (
            self.open_hook(path, read_only)
            if self.open_hook is not None
            else FakeDocument(path=path, read_only=read_only)
        )
        self.documents.append(doc)
        return doc


@dataclass
class FakeApp:
    """Stand-in for the ZWCAD ``Application`` COM object ``create_app`` returns."""

    Version: str = "2026"  # noqa: N815 - COM property name
    HWND: int = 424242  # noqa: N815 - COM property name
    Visible: bool | None = None  # noqa: N815 - COM property name
    Documents: FakeDocuments = field(default_factory=FakeDocuments)  # noqa: N815
    sysvars: dict[str, Any] = field(default_factory=dict)
    #: sysvar names whose SetVariable call should raise, to exercise the fatal-sysvar path.
    failing_sysvars: frozenset[str] = frozenset()
    quit_calls: int = 0
    visible_setter_fails: bool = False

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "Visible" and getattr(self, "visible_setter_fails", False):
            raise RuntimeError("Visible setter failed (simulated)")
        object.__setattr__(self, name, value)

    def SetVariable(self, name: str, value: Any) -> None:  # noqa: N802 - COM method name
        if name in self.failing_sysvars:
            raise RuntimeError(f"SetVariable({name!r}) failed (simulated)")
        self.sysvars[name] = value

    def Quit(self) -> None:  # noqa: N802 - COM method name
        self.quit_calls += 1


@dataclass
class FakeComBackend:
    """Records ``create_app``/``kill_process_tree`` calls; hands out ``FakeApp`` instances.

    ``app_factory`` lets a test customize each created app (e.g. to make a
    document's ``SaveAs`` hang past a converter's ``timeout_s``, for the
    timeout/restart test).
    """

    app_factory: Callable[[str], FakeApp] = field(default=lambda prog_id: FakeApp())
    create_app_calls: list[str] = field(default_factory=list)
    kill_process_tree_calls: list[int] = field(default_factory=list)
    apps: list[FakeApp] = field(default_factory=list)
    #: ProgIDs create_app should raise for, to exercise the fallback/unavailable paths.
    fail_prog_ids: frozenset[str] = frozenset()

    def create_app(self, prog_id: str) -> FakeApp:
        self.create_app_calls.append(prog_id)
        if prog_id in self.fail_prog_ids:
            raise RuntimeError(f"no such ProgID (simulated): {prog_id}")
        app = self.app_factory(prog_id)
        self.apps.append(app)
        return app

    def kill_process_tree(self, pid: int) -> None:
        self.kill_process_tree_calls.append(pid)
