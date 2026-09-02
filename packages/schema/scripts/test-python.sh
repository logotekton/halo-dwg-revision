#!/usr/bin/env bash
# Runs the pytest suite for the generated Python bindings.
#
#   packages/schema/scripts/test-python.sh
#
# Requires uv (Python 3.12 is fetched by uv itself):
#   export PATH="$HOME/.local/bin:$PATH"
#
# The package is not installed: the suite runs straight out of the tree with
# PYTHONPATH, so a checkout needs nothing beyond uv. Tests that need the
# generated pydantic models skip when gen-python.sh has not been run.
set -euo pipefail

PKG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_ROOT="$PKG_ROOT/gen/python"

if ! command -v uv >/dev/null 2>&1; then
  echo 'test-python.sh: uv not found. export PATH="$HOME/.local/bin:$PATH" and re-run.' >&2
  exit 3
fi

cd "$PY_ROOT"
PYTHONPATH="$PY_ROOT" uv run --python 3.12 --no-project \
  --with 'pydantic>=2.9' \
  --with 'jsonschema>=4.23' \
  --with 'referencing>=0.35' \
  --with 'pytest>=8.3' \
  python -m pytest tests "$@"
