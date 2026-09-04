#!/usr/bin/env bash
# Builds the halo_engine PyInstaller onedir sidecar.
#
# Output: engine/dist/halo-engine/halo-engine (+ _internal/), or
# engine/dist/halo-engine/halo-engine.exe on Windows -- matching the
# `engine/dist/halo-engine/` -> electron-builder `extraResources` contract in
# docs/contracts/r1.md (carried over from docs/contracts/wave-2.md
# "패키징"). Run standalone (`engine/scripts/build-sidecar.sh`), as step 1 of
# `tools/package.sh` (macOS), or as a step of
# `.github/workflows/windows-installer.yml` (Windows, run under Git Bash --
# originally macOS-only as a W2-08 packaging spike, made cross-platform by
# R1-00b per docs/briefs/R1-00b.md).
#
# PyInstaller is pulled in via `uv run --with` (an ephemeral overlay for this
# invocation only) rather than added to engine/pyproject.toml's dev group --
# this script does not own that file, so the sidecar build tool stays out of
# the project's real dependency set / uv.lock.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ENGINE_DIR"

# Git Bash on windows-latest reports itself via `uname -s` as
# MINGW64_NT-... (MSYS2-based); the ambient `OS=Windows_NT` env var (set by
# cmd.exe/PowerShell and inherited by Git Bash) is a second, redundant
# signal in case a future runner's `uname` ever changes shape.
IS_WINDOWS=0
case "$(uname -s 2>/dev/null || true)" in
  MINGW* | MSYS* | CYGWIN*) IS_WINDOWS=1 ;;
esac
if [ "${OS:-}" = "Windows_NT" ]; then IS_WINDOWS=1; fi

PYINSTALLER_VERSION="6.22.0" # CLAUDE.md pin "PyInstaller 6.22"
EXE_SUFFIX=""
[ "$IS_WINDOWS" = 1 ] && EXE_SUFFIX=".exe"
BIN="dist/halo-engine/halo-engine${EXE_SUFFIX}"

echo "== halo_engine sidecar build =="
echo "engine dir: $ENGINE_DIR"
echo "windows: $IS_WINDOWS"

echo "-- uv sync (engine deps) --"
uv sync --frozen

echo "-- pyinstaller ${PYINSTALLER_VERSION} (onedir, halo-engine.spec) --"
rm -rf build dist
uv run --with "pyinstaller==${PYINSTALLER_VERSION}" pyinstaller halo-engine.spec --clean --noconfirm

if [ ! -x "$BIN" ]; then
  echo "FAIL: expected executable not found at $ENGINE_DIR/$BIN" >&2
  exit 1
fi

SIZE=$(du -sh dist/halo-engine | cut -f1)
echo "-- sidecar built: $ENGINE_DIR/$BIN (onedir size: $SIZE) --"

# Escape hatch (docs/briefs/R1-00b.md "Defaults for ambiguity"): if the
# windows-latest runner's port binding turns out to be flaky for this
# smoke check, set HALO_SIDECAR_SMOKE=0 to skip it without failing the
# build. Default is to always run the check.
if [ "${HALO_SIDECAR_SMOKE:-1}" != "1" ]; then
  echo "-- smoke check: skipped (HALO_SIDECAR_SMOKE=0) --"
  echo "== sidecar build OK (unverified) =="
  exit 0
fi

echo "-- smoke check: standalone READY handshake --"
STDOUT_LOG="$(mktemp)"
trap 'rm -f "$STDOUT_LOG"' EXIT
"$BIN" serve --dev --port 0 --token dev >"$STDOUT_LOG" 2>/dev/null &
SIDECAR_PID=$!

READY_LINE=""
for _ in $(seq 1 100); do # up to 20s, matching the sidecar protocol's READY timeout
  if [ -s "$STDOUT_LOG" ]; then
    READY_LINE="$(head -n1 "$STDOUT_LOG")"
    break
  fi
  sleep 0.2
done

# The packaged `halo-engine(.exe)` launcher spawns the real Python process
# as a *child* rather than exec-replacing itself (confirmed on both modes,
# docs/dev/engine-sidecar.md "스폰 pid != 서버 pid"), so `$SIDECAR_PID` alone
# may not be the process actually holding stdout/the port on every
# platform. On Windows, `kill` (SIGTERM emulation) does not reliably reach
# that child, so end the whole process tree via `taskkill /T`. The `//`
# prefix (instead of `/`) stops Git Bash's MSYS path-conversion layer from
# rewriting `/PID`/`/T`/`/F` into Windows paths before taskkill sees them --
# a well-known Git Bash gotcha, not a typo.
if [ "$IS_WINDOWS" = 1 ]; then
  taskkill //PID "$SIDECAR_PID" //T //F >/dev/null 2>&1 || true
else
  kill "$SIDECAR_PID" 2>/dev/null || true
fi
wait "$SIDECAR_PID" 2>/dev/null || true

if [[ "$READY_LINE" != *'"event"'*'"ready"'* ]]; then
  echo "FAIL: sidecar did not print a READY line within 20s. Got: '$READY_LINE'" >&2
  exit 1
fi
echo "READY line: $READY_LINE"
echo "== sidecar build OK =="
