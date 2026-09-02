#!/usr/bin/env bash
# Generates the pydantic v2 bindings from the JSON Schema sources.
#
#   src/**/*.schema.json  ->  gen/python/halo_schema/models/**
#                         ->  gen/python/halo_schema/schemas/**  (verbatim copy)
#
# Output is committed. Run it after every schema change, together with
# `pnpm --filter @halo-cad/schema build`, and commit both trees.
#
# Requires uv (Python 3.12 is fetched by uv itself):
#   export PATH="$HOME/.local/bin:$PATH"
set -euo pipefail

PKG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PKG_ROOT"

# Pinned so the committed output is reproducible on any machine.
DATAMODEL_CODEGEN_VERSION="0.76.0"
PYTHON_VERSION="3.12"

PACKAGE_DIR="gen/python/halo_schema"
MODELS_DIR="$PACKAGE_DIR/models"
SCHEMAS_DIR="$PACKAGE_DIR/schemas"

if ! command -v uv >/dev/null 2>&1; then
  cat >&2 <<'EOF'
gen-python.sh: uv not found.

  export PATH="$HOME/.local/bin:$PATH"

and re-run. Without uv the pydantic bindings cannot be regenerated; the
TypeScript build and the vitest suite do not depend on this script.
EOF
  exit 3
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# datamodel-code-generator resolves `$ref` by URL and would try to download the
# reserved `schema.halo-cad.internal` origin, so it reads a copy with
# file-relative references instead. See scripts/localize-refs.mjs.
node scripts/localize-refs.mjs "$TMP_DIR/schemas"

rm -rf "$MODELS_DIR"
uv run --python "$PYTHON_VERSION" --no-project \
  --with "datamodel-code-generator==$DATAMODEL_CODEGEN_VERSION" \
  datamodel-codegen \
  --input "$TMP_DIR/schemas" \
  --input-file-type jsonschema \
  --output "$MODELS_DIR" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version "$PYTHON_VERSION" \
  --disable-timestamp \
  --use-schema-description \
  --use-field-description \
  --use-standard-collections \
  --use-union-operator \
  --use-double-quotes \
  --field-constraints \
  --collapse-root-models \
  --formatters black \
  --formatters isort

# The schemas travel with the package so `halo_schema.validation` can enforce
# the conditional rules (ADR-0003 height comparisons, evidence requirements)
# that pydantic models cannot express. Byte-identical to src/; the vitest suite
# fails if the two ever drift.
rm -rf "$SCHEMAS_DIR"
while IFS= read -r rel; do
  mkdir -p "$SCHEMAS_DIR/$(dirname "$rel")"
  cp "src/$rel" "$SCHEMAS_DIR/$rel"
done < <(cd src && find . -name '*.schema.json' | sed 's|^\./||' | sort)

echo "generated $MODELS_DIR and refreshed $SCHEMAS_DIR"
