#!/usr/bin/env bash
# Parser crosscheck over the synthetic fixtures (W2-04, ADR-0002 decision 6).
#
# Produces a LayerStatsDocument from each of the three parsers for every
# F01..F10 DXF, runs the three pairwise `halo-engine crosscheck` comparisons,
# and rewrites the result table in docs/spikes/crosscheck-fixtures.md.
#
# All three parsers read the *same* R2018 DXF bytes, which is the whole point
# of ADR-0002 decision 2 ("뷰어와 엔진은 같은 정본 바이트를 파싱한다"): the
# `file_sha256` of the three documents then matches and the comparison is not
# muddied by a conversion. acad-bridge can also read the .dwg fixtures, but a
# DWG-converted input loses the X-TITLE INSERT outright (a *count* gap, which
# is never whitelistable) and is therefore not what this script compares.
#
# Usage: tools/crosscheck.sh [--no-build] [--out-dir DIR] [--only F06]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BUILD=1
OUT_DIR="${TMPDIR:-/tmp}/halo-cad-crosscheck"
ONLY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --no-build) BUILD=0 ;;
    --out-dir) OUT_DIR="$2"; shift ;;
    --only) ONLY="$2"; shift ;;
    -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
  shift
done

# F10 is a file *pair* (host + its XREF grid), so it contributes two documents.
FIXTURES="F01 F02 F03 F04 F05 F06 F07 F08 F09 F10_grid F10_host"
if [ -n "$ONLY" ]; then FIXTURES="$ONLY"; fi

# `<a>__<b>`: the crosscheck runs with <a> as --ref and <b> as --other.
PAIRS="ezdxf__mlightcad ezdxf__acad-ts mlightcad__acad-ts"

mkdir -p "$OUT_DIR"
step() { printf '\n\033[1;34m== %s\033[0m\n' "$1"; }

if [ "$BUILD" = 1 ]; then
  step "build @halo-cad/schema, cad-core, acad-bridge"
  pnpm install --frozen-lockfile >/dev/null
  # cad-core's stats script loads packages/cad-core/dist, acad-bridge's CLI is
  # bin/acad-bridge.mjs; both need @halo-cad/schema's generated types first.
  pnpm --filter @halo-cad/schema build >/dev/null
  pnpm --filter @halo-cad/cad-core build >/dev/null
  pnpm --filter @halo-cad/acad-bridge build >/dev/null
fi

step "stats: three producers x $(echo "$FIXTURES" | wc -w | tr -d ' ') fixtures -> $OUT_DIR"
for f in $FIXTURES; do
  dxf="fixtures/generated/$f.dxf"
  if [ ! -f "$dxf" ]; then
    echo "missing $dxf -- run \`cd fixtures/gen && uv run python -m fixtures_gen --out ../generated --truth ../truth\`" >&2
    exit 1
  fi
  ( cd engine && uv run halo-engine stats "../$dxf" --out "$OUT_DIR/$f.ezdxf.json" >/dev/null )
  node tools/crosscheck/mlightcad-stats.mjs "$dxf" --out "$OUT_DIR/$f.mlightcad.json" >/dev/null
  node packages/acad-bridge/bin/acad-bridge.mjs stats "$dxf" --out "$OUT_DIR/$f.acad-ts.json" >/dev/null
  printf '   %s\n' "$f"
done

step "crosscheck: 3 pairs x $(echo "$FIXTURES" | wc -w | tr -d ' ') fixtures"
worst=GREEN
for f in $FIXTURES; do
  line="   $f"
  for pair in $PAIRS; do
    a="${pair%%__*}"; b="${pair##*__}"
    status=$( cd engine && uv run halo-engine crosscheck \
      --ref "$OUT_DIR/$f.$a.json" --other "$OUT_DIR/$f.$b.json" \
      --out "$OUT_DIR/$f.$a-vs-$b" | tail -1 )
    line="$line  $a/$b=$status"
    case "$status" in
      RED) worst=RED ;;
      AMBER) [ "$worst" = RED ] || worst=AMBER ;;
    esac
  done
  printf '%s\n' "$line"
done

step "docs/spikes/crosscheck-fixtures.md"
uv run --project engine python tools/crosscheck/render-fixture-table.py \
  --reports "$OUT_DIR" --fixtures "$FIXTURES" --pairs "$PAIRS" \
  --out docs/spikes/crosscheck-fixtures.md

printf '\n'
case "$worst" in
  GREEN) printf '\033[1;32mCROSSCHECK: all GREEN\033[0m\n' ;;
  AMBER) printf '\033[1;33mCROSSCHECK: GREEN/AMBER (every AMBER has a whitelist reason)\033[0m\n' ;;
  RED)   printf '\033[1;31mCROSSCHECK: RED — see docs/spikes/crosscheck-fixtures.md\033[0m\n'; exit 1 ;;
esac
