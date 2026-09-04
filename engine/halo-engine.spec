# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the halo_engine sidecar.

Produces an *onedir* bundle at `engine/dist/halo-engine/` whose entry point
is `engine/dist/halo-engine/halo-engine` (`halo-engine.exe` on Windows) --
the layout the packaging contract (`docs/contracts/r1.md`, carried over from
`docs/contracts/wave-2.md` "패키징") pins for electron-builder's
`extraResources` (-> `<resources>/engine/`). Originally built for macOS
arm64 only (W2-08); R1-00b (`docs/briefs/R1-00b.md`) made this spec build on
`windows-latest` too, for `.github/workflows/windows-installer.yml`.

Build with `engine/scripts/build-sidecar.sh` (never invoke `pyinstaller`
directly -- the script pins the PyInstaller version via `uv run --with` so
neither `pyproject.toml` nor `uv.lock` need to gain a dev dependency for it,
and it runs from the right cwd for the relative paths below).

Heavy/dynamic dependencies are force-collected with `collect_all` even though
today's `halo_engine` source does not import them yet (`model/`, `rules/`,
`geometry/` are still stubs) -- the whole point of this spike is proving the
binary/data collection works *before* other Wave-2/3 tasks start relying on
it at runtime:
  - ifcopenshell: schema/express data files + `ifcopenshell.api`'s dynamically
    imported submodules (dispatched by string, invisible to static analysis).
  - shapely: bundles its own GEOS dylibs under `shapely/.dylibs/`.
  - manifold3d, trimesh: same pattern (data + extension modules).
`copy_metadata` is added for every package `api/routers/system.py`'s
`/health` endpoint resolves via `importlib.metadata.version()`, so the
bundled binary reports real versions instead of "unknown".
"""

import sys

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = [
    # typer's Click app + optional shell-completion detection (imported by
    # name, not by static reference, when --install-completion is touched).
    "click",
    "shellingham",
    # uvicorn resolves its event loop / HTTP protocol implementation by
    # string at runtime ("auto"), which static analysis can't see. Our
    # pyproject pins plain `uvicorn` (no `[standard]` extras -- CLAUDE.md
    # "uvloop 제외"), so only the asyncio loop and h11 HTTP implementation
    # are actually installed; uvicorn.workers (gunicorn integration) and the
    # websocket/uvloop backends are deliberately left out since their
    # optional deps (gunicorn, websockets, wsproto, uvloop) aren't installed.
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.utils",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
]

for _pkg in ("ifcopenshell", "shapely", "manifold3d", "trimesh"):
    _datas, _binaries, _hidden = collect_all(_pkg)
    # collect_all() walks the whole package tree, which also sweeps up each
    # library's own test suite (e.g. shapely.tests.*, shapely.conftest) --
    # dev-only weight with no runtime purpose here, and the surest source of
    # the excludes= leak below (shapely's tests import hypothesis).
    _datas = [d for d in _datas if ".tests" not in d[0] and "conftest" not in d[0]]
    _hidden = [h for h in _hidden if ".tests" not in h and not h.endswith(".conftest")]
    datas += _datas
    binaries += _binaries
    hiddenimports += _hidden

for _pkg in ("ezdxf", "shapely", "manifold3d", "trimesh", "ifcopenshell", "numpy", "fastapi"):
    datas += copy_metadata(_pkg)

# comtypes (ADR-0007) is a Windows-only runtime dependency (`sys_platform ==
# 'win32'` marker in engine/pyproject.toml) used by the ZWCAD COM bridge
# (`halo_engine.compare.zwcad`, R1-02). It is simply not installed in the
# build venv on macOS/Linux, so `collect_all`/`copy_metadata` must only run
# when actually building on Windows -- calling them otherwise would raise
# ModuleNotFoundError and break the mac sidecar build.
if sys.platform == "win32":
    _comtypes_datas, _comtypes_binaries, _comtypes_hidden = collect_all("comtypes")
    datas += _comtypes_datas
    binaries += _comtypes_binaries
    hiddenimports += _comtypes_hidden

a = Analysis(  # noqa: F821 (PyInstaller injects Analysis/PYZ/EXE/COLLECT globals)
    ["src/halo_engine/__main__.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # pydantic ships optional plugin shims (pydantic.mypy, pydantic.v1
    # .mypy/._hypothesis_plugin) that `import mypy`/`import hypothesis` at
    # module level; PyInstaller's static analysis can't tell those imports
    # are dead unless the plugin is enabled, so they get bundled whenever the
    # dev tools happen to be installed in the build venv (engine's uv sync
    # pulls in its whole dev dependency-group by default). None of this
    # ships-quality code is reachable at sidecar runtime -- exclude it.
    excludes=["mypy", "hypothesis", "pytest", "_pytest", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="halo-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    # `target_arch` only means anything to PyInstaller's macOS Mach-O linker
    # (arm64/x86_64/universal2); on Windows/Linux it must be left at the
    # default (None) or PyInstaller raises on non-Darwin hosts.
    target_arch="arm64" if sys.platform == "darwin" else None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="halo-engine",
)
