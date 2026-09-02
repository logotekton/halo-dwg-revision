#!/usr/bin/env bash
# Halo CAD local verification entry point. Fable runs this on every returned task.
# Usage: tools/verify.sh [--e2e] [--no-install]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

E2E=0; INSTALL=1
for a in "$@"; do
  case "$a" in
    --e2e) E2E=1 ;;
    --no-install) INSTALL=0 ;;
    *) echo "unknown arg: $a" >&2; exit 2 ;;
  esac
done

fail=0
step() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }
ok()   { printf '\033[1;32m   ok: %s\033[0m\n' "$1"; }
bad()  { printf '\033[1;31m   FAIL: %s\033[0m\n' "$1"; fail=1; }

# ---------- forbidden strings: ODA File Converter ----------
step "forbidden: ODA File Converter references"
if grep -rniE 'odafc|ODAFileConverter|opendesign\.com' \
     --include='*.ts' --include='*.tsx' --include='*.js' --include='*.mjs' --include='*.py' --include='*.json' --include='*.yaml' --include='*.yml' --include='*.toml' \
     --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=.claude --exclude-dir=dist --exclude-dir=out --exclude-dir=.venv --exclude-dir=docs \
     . | grep -v 'tools/verify.sh' ; then
  bad "ODA references found (see above)"
else
  ok "no ODA references"
fi

# ---------- GPL boundary: libredwg only inside packages/dwg-io-gpl and desktop convert wiring ----------
step "GPL boundary: @mlightcad/libredwg-* imports"
viol=$(grep -rnE "@mlightcad/libredwg-(web|converter)" \
        --include='*.ts' --include='*.tsx' --include='*.js' --include='*.mjs' \
        --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=out \
        apps packages 2>/dev/null \
      | grep -vE '^packages/dwg-io-gpl/|^apps/desktop/src/main/ipc/convert\.ts|^apps/desktop/electron\.vite\.config\.ts|^apps/web/lint-fixtures/' || true)
if [ -n "$viol" ]; then echo "$viol"; bad "libredwg imported outside allowed locations"; else ok "boundary respected"; fi

# ---------- height rule: CH must not be equality-compared with SL/FL/FLOOR_HEIGHT (heuristic) ----------
step "height rule heuristic (ADR-0003)"
viol=$(grep -rnE '\b(ch|CH|ceiling_height)\b\s*(==|!=|===|!==)\s*\b(sl|SL|fl|FL|floor_height|FLOOR_HEIGHT|story_height)\b|\b(sl|SL|fl|FL|floor_height|FLOOR_HEIGHT|story_height)\b\s*(==|!=|===|!==)\s*\b(ch|CH|ceiling_height)\b' \
        --include='*.ts' --include='*.tsx' --include='*.py' \
        --exclude-dir=node_modules --exclude-dir=.git --exclude-dir=dist --exclude-dir=.venv \
        apps packages engine 2>/dev/null || true)
if [ -n "$viol" ]; then echo "$viol"; bad "CH compared for equality with a structural height"; else ok "no CH/SL equality comparisons"; fi

# ---------- TypeScript workspace ----------
if [ -f pnpm-lock.yaml ]; then
  step "pnpm install --frozen-lockfile"
  if [ "$INSTALL" = 1 ]; then pnpm install --frozen-lockfile >/dev/null && ok "installed" || bad "pnpm install"; else ok "skipped (--no-install)"; fi
  step "pnpm -r lint / typecheck / test"
  pnpm -r --if-present run lint      && ok "lint"      || bad "lint"
  pnpm -r --if-present run typecheck && ok "typecheck" || bad "typecheck"
  pnpm -r --if-present run test      && ok "test"      || bad "test"
  if [ -f tools/license-check.mjs ]; then
    step "license-check"
    node tools/license-check.mjs && ok "licenses" || bad "licenses"
  fi
  if [ "$E2E" = 1 ]; then
    step "e2e"
    pnpm -r --if-present run e2e && ok "e2e" || bad "e2e"
  fi
else
  step "TypeScript workspace"; ok "skipped (no pnpm-lock.yaml yet)"
fi

# ---------- Python engine ----------
if [ -f engine/pyproject.toml ]; then
  step "engine: uv sync / ruff / mypy / pytest"
  if ! command -v uv >/dev/null 2>&1; then
    bad "uv not installed"
  else
    ( cd engine
      if [ -f uv.lock ]; then uv sync --frozen --quiet && ok "uv sync" || bad "uv sync"; fi
      uv run ruff check . && ok "ruff" || bad "ruff"
      uv run ruff format --check . && ok "ruff format" || bad "ruff format"
      if grep -q '\[tool.mypy\]' pyproject.toml; then uv run mypy && ok "mypy" || bad "mypy"; fi
      uv run pytest -q && ok "pytest" || bad "pytest"
    )
  fi
else
  step "Python engine"; ok "skipped (no engine/pyproject.toml yet)"
fi

echo
if [ "$fail" = 0 ]; then printf '\033[1;32mVERIFY: PASS\033[0m\n'; else printf '\033[1;31mVERIFY: FAIL\033[0m\n'; exit 1; fi
