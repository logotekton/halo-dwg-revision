#!/usr/bin/env bash
# Builds the halo_engine PyInstaller onedir sidecar (W2-08 packaging spike).
#
# Output: engine/dist/halo-engine/halo-engine (+ _internal/), matching the
# `engine/dist/halo-engine/` -> electron-builder `extraResources` contract in
# docs/contracts/wave-2.md. Run standalone (`engine/scripts/build-sidecar.sh`)
# or as step 1 of `tools/package.sh`.
#
# PyInstaller is pulled in via `uv run --with` (an ephemeral overlay for this
# invocation only) rather than added to engine/pyproject.toml's dev group --
# W2-08 does not own that file, so the sidecar build tool stays out of the
# project's real dependency set / uv.lock.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ENGINE_DIR"

PYINSTALLER_VERSION="6.22.0" # CLAUDE.md pin "PyInstaller 6.22"
BIN="dist/halo-engine/halo-engine"

echo "== halo_engine sidecar build =="
echo "engine dir: $ENGINE_DIR"

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

kill "$SIDECAR_PID" 2>/dev/null || true
wait "$SIDECAR_PID" 2>/dev/null || true

if [[ "$READY_LINE" != *'"event"'*'"ready"'* ]]; then
  echo "FAIL: sidecar did not print a READY line within 20s. Got: '$READY_LINE'" >&2
  exit 1
fi
echo "READY line: $READY_LINE"
echo "== sidecar build OK =="
