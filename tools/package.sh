#!/usr/bin/env bash
# Halo CAD macOS arm64 packaging pipeline (W2-08). Produces:
#   engine/dist/halo-engine/       PyInstaller onedir sidecar
#   dist/Halo CAD-<version>-arm64.dmg
#   dist/Halo CAD-<version>-arm64-mac.zip
#
# Order (fixed by docs/briefs/W2-08.md): sidecar build -> `pnpm build` ->
# electron-builder. Any step failing aborts the whole pipeline immediately.
#
# No code signing identity / notarization in this environment (Xcode CLT
# only) -- electron-builder ad-hoc signs (identity: null). Gatekeeper bypass
# for a locally-built, unsigned app is documented in docs/dev/packaging.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

step() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }

step "1/3 build sidecar (PyInstaller onedir)"
engine/scripts/build-sidecar.sh

step "2/3 pnpm build (apps/web dist + apps/desktop main/preload)"
pnpm build

step "3/3 electron-builder (dmg + zip, arm64)"
pnpm --filter @halo-cad/desktop build:app

DMG=$(ls dist/*.dmg 2>/dev/null | head -n1 || true)
if [ -z "$DMG" ]; then
  echo "FAIL: no .dmg produced under $ROOT/dist" >&2
  exit 1
fi

step "done"
echo "sidecar:  $ROOT/engine/dist/halo-engine/halo-engine ($(du -sh engine/dist/halo-engine | cut -f1))"
echo "dmg:      $DMG ($(du -sh "$DMG" | cut -f1))"
for z in dist/*-mac.zip; do
  [ -e "$z" ] && echo "zip:      $z ($(du -sh "$z" | cut -f1))"
done
echo "app:      $ROOT/dist/mac-arm64/Halo CAD.app"
