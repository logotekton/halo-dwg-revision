# @halo-cad/acad-bridge

CLI bridge around [`@node-projects/acad-ts@3.1.0`](https://github.com/node-projects/acad-ts) (MIT,
an ACadSharp port): DWG/DXF conversion and the third parser's layer statistics for ADR-0002's
crosscheck (`docs/contracts/stats-definition.md`). Node 24 ESM.

## CLI usage

```bash
pnpm --filter @halo-cad/acad-bridge build     # -> bin/acad-bridge.mjs
node packages/acad-bridge/bin/acad-bridge.mjs <command> ...
```

| Command | Usage | Notes |
|---|---|---|
| `dwg2dxf` | `dwg2dxf <in.dwg> <out.dxf> [--version AC1032]` | Default target AC1032 (R2018, UTF-8 era). |
| `dxf2dwg` | `dxf2dwg <in.dxf> <out.dwg> [--version AC1027]` | Default target AC1027 (R2013-2017), per the brief. |
| `stats` | `stats <in.dwg\|in.dxf> --out <json>` | `LayerStatsDocument`, `producer: {name: "acad-ts", version}`, validated with `@halo-cad/schema`'s `validateLayerStats` before writing. |
| `info` | `info <in.dwg\|in.dxf>` | Version, code page, entity counts by type. |

Every `stats`/`dwg2dxf`/`dxf2dwg` run also writes a `<out>.drops.json` sidecar (extension replaced,
e.g. `f06.acad.json` -> `f06.acad.drops.json`) -- see "Drop report" below. Output is deterministic:
no timestamps, stable key order (CLAUDE.md rule 7).

Format (`dwg`/`dxf`) is detected from the input's file extension.

## Supported / unsupported

acad-ts is a large, actively-ported library; this table is scoped to what
`fixtures/generated/F01..F10` actually exercise, not an exhaustive audit.

| Item | Status | Notes |
|---|---|---|
| LINE, LWPOLYLINE, POLYLINE (2D/3D), ARC, CIRCLE, ELLIPSE, SPLINE | Supported | Read, written, round-trip exact on F01-F09. |
| TEXT, MTEXT, INSERT, ATTRIB/ATTDEF, HATCH (incl. holes, ANSI/user patterns) | Supported | |
| **MULTILEADER** | Supported | Contrary to the brief's example guess -- acad-ts has a real `MultiLeader` class (`Entities/MultiLeader.ts`), not a proxy/unknown fallback. |
| **Gradient HATCH** | Supported | Also contrary to the brief's guess -- `HatchGradientPattern` is a real, populated class. |
| DIMENSION (linear/aligned/angular/radius/diameter/ordinate), LEADER | Supported | `DimensionArc`'s `objectName` is the DXF token `ARC_DIMENSION`, not `DIMENSION` -- normalised in `acad/entity-types.ts`. |
| XREF (INSERT of an external block record) | Supported | F10_host round-trips clean; the XREF's own geometry lives only in F10_grid, as expected (acad-ts does not resolve XREF contents across files, matching ADR-0002's own working-DXF-embeds-XREF design). |
| Non-ASCII (Korean) text decoding, any DXF version | **Broken** | See "Known acad-ts gaps" #3 -- not limited to legacy cp949. |
| A BLOCK and a LAYER sharing one name | **Broken** | See "Known acad-ts gaps" #1. Affects F06 and F10_grid (both use the shared `X-TITLE` title-block fixture, whose layer and block are both named `X-TITLE`). |
| XDATA, extended dictionaries | Not exercised | None of F01-F10 use them (`grep -rn "xdata\|extension_dict" fixtures/gen/src` is empty) -- `CadObject.extendedData`/`.xDictionary` exist in the type surface, so this package does not claim they are unsupported, only untested. |

## Known acad-ts gaps (evidence for ADR-0002)

Found while implementing this bridge; each is isolated with a minimal reproduction, not just
observed once in a fixture.

1. **A BLOCK and a LAYER sharing a name breaks INSERT block resolution.** Minimal repro (`Layer
   "DUP"` + `BlockRecord "DUP"` + an `Insert` referencing it, written to DXF, read back):
   `insert.block` comes back `null` and `DxfReader` emits `Table reference with handle: null |
   name: DUP not found for Insert with handle N`. With distinct names it resolves fine. F06 and
   F10_grid both place their title block's INSERT on a layer named after the block itself
   (`X-TITLE`/`X-TITLE`), which is valid, ordinary DXF (layer names and block names are separate
   symbol tables) -- and hits this exactly. Effect: the INSERT's `block` is `null`, so this
   package's `stats` records it under `insert_by_block["<unresolved>"]` instead of the real block
   name, and the DWG *writer* silently drops the entity entirely (confirmed: `F06.dxf` has 8
   top-level INSERTs; `F06.dwg` read back has 7). This is why `fixtures/generated/F06.dwg`'s
   `stats`/`info` `count_by_type.INSERT` is **7**, not the 8 that `fixtures/generated/F06.dxf`
   (and `fixtures/truth/F06.json`) show -- see "Round-trip results" and this task's report
   "Deviations from brief".
2. **`SeqendCollection`-backed arrays can contain their own terminator as a plain element.**
   `Insert.attributes` (`SeqendCollection<AttributeEntity>`) and `Polyline.vertices`
   (`SeqendCollection<Entity>`) are typed to hold only real members, but at runtime the array can
   also contain the trailing `SEQEND`/`VERTEX` object as a literal element (not only via the
   separate `.seqend` property the type suggests). Consumers that trust the generic type parameter
   break: acad-ts's own `PolylineExtensions._toXYZ` throws `Cannot read properties of undefined
   (reading 'x')` inside `Polyline2D.getBoundingBox()` when this happens (hit on F01, which has one
   old-style 2D POLYLINE). Worked around in two places: `acad/walk.ts` filters
   `Insert.attributes` by `objectName` before yielding, and `acad/stats-builder.ts`'s `unionBBox`
   wraps `entity.getBoundingBox()` in try/catch (bbox is an optional stats field, so the entity is
   just excluded from the union with a drop entry, rather than crashing the whole `stats` run).
3. **Non-ASCII DXF text (Korean) decodes to mojibake -- in BOTH the UTF-8-era and the legacy
   cp949 fixture.** Originally investigated for `F03_r2000_cp949.dxf` (R2000, `$DWGCODEPAGE` =
   `ANSI_949`, confirmed correctly cp949-round-tripped by ezdxf itself per
   `fixtures/gen/tests/test_cp949_roundtrip.py`), where TEXT values read back as e.g. `°Å½Ç` where
   the source is `거실` ("living room") -- Latin-1-shaped garbage, not Hangul. But the *same*
   corruption shows up reading the **primary R2018/AC1032 UTF-8 fixtures directly**, e.g.
   `F03.dxf`'s first few TEXT values come back `"ê±°ì‹¤"`, `"ì¹¨ì‹¤1"`, ... -- which is exactly what
   `"거실"`/`"침실1"` look like when valid UTF-8 bytes are read one byte at a time as Latin-1/ANSI
   instead of being UTF-8-decoded. So this is not specific to legacy code pages: acad-ts's ASCII
   DXF reader appears to always decode multi-byte text as a single-byte codepage, even for
   R2007+/UTF-8-era files where DXF text is UTF-8 bytes directly (no `$DWGCODEPAGE` escaping
   involved at all). This affects every fixture with non-ASCII text read directly from DXF
   (F01, F03, F06, F07, F08, F09 all have Korean strings) and is very likely why this package's
   `text_hash` does not match `fixtures/truth/F06.json` despite an otherwise-identical algorithm
   (see below). Per the brief's "Defaults for ambiguity" ("한글 인코딩 문제가 나오면 우회하지 말고
   드롭 리포트와 Questions에 기록"), this package does not implement its own decoder to paper over
   it; `src/acad/cp949.test.ts` documents the R2000/cp949 case and checks only that whatever
   acad-ts decodes stays self-consistent (`text_hash`/`text_count` unchanged) through a DWG round
   trip. **This is the single highest-priority finding in this report for ADR-0002** -- see this
   task's report "Questions for gate".
4. **Benign notification noise on any DWG that has been through this package's writers.**
   Re-reading a `dxf2dwg`-produced DWG emits ~25-26 `[Warning] DWG VisualStyle payload is only
   partially mapped; preserving base object data for <name> ...` notifications (once per standard
   AutoCAD default visual style `DwgWriter` creates) -- the message says it preserves the base
   object, and nothing entity/geometry-related is affected. Similarly, re-reading a *DXF* written
   from a *DWG-read* document that has ATTRIB entities on the `Standard` text style produces
   `Table reference ... Standard not found for AttributeEntity ...` and `Repeated handle found
   NNN` notifications -- also confirmed benign by direct comparison (F02's `stats` totals and
   entity handle list are byte-identical before and after; see `roundtrip.test.ts`). Both classes
   are still recorded in `*.drops.json` (`reason: "read-notification"`) for full transparency, but
   are not evidence of data loss the way an `acad-ts-unsupported`/`stats-schema-unsupported-type`
   drop is.

## `stats`: schema and contract notes

- `producer` is the schema's `{name, version}` object (`packages/schema/src/ndj/document.schema.json#/$defs/producer`),
  not the bare string `"acad-ts"` docs/contracts/stats-definition.md's prose describes -- the
  schema is what `validateLayerStats` actually checks, and is treated as authoritative wherever the
  two disagree (see this task's report "Deviations from brief" for every such case).
- `count_by_type`'s keys are the schema's closed `entity_type` enum
  (`packages/schema/src/ndj/entity.schema.json#/$defs/entity_type`), which uses **`MLEADER`**, not
  `MULTILEADER` (acad-ts's own, and the real DXF group-code, type name) -- `acad/entity-types.ts`
  renames it. Anything acad-ts reads that has no slot in that enum at all (e.g. `VIEWPORT`, none of
  which appear in F01-F10) is excluded from `stats` output and recorded as a
  `stats-schema-unsupported-type` drop, per the schema's own doc comment ("Anything the parser
  cannot map to one of these is reported as a whitelist violation by the crosscheck, not emitted as
  NDJ").
- `count_by_type`/`entity_count` exclude ATTRIB (`stats-definition.md`: "ATTRIB·SEQEND·VERTEX는
  세지 않는다(소유 엔티티에 속함)"); ATTRIB still contributes to `text_count`/`text_hash` under its
  *own* layer's bucket. Confirmed against `fixtures/truth/F06.json` (post-merge, now a real
  `LayerStatsDocument`): `entity_count: 86`, `text_count: 40` (30 TEXT + 10 ATTRIB), no `ATTRIB` key
  in `count_by_type` -- all three match this package's output on `F06.dxf` exactly.
- `text_hash` on F06 does not match `fixtures/truth/F06.json` (`3b5647d80a0bb067` vs
  `125bac30a2dbb6b8`) despite this package implementing the exact documented algorithm (confirmed
  identical to `fixtures/gen/src/fixtures_gen/stats.py`'s `_text_hash`/`_nfc_sorted_join`, W2-03's
  updated implementation). Root cause: "Known acad-ts gaps" #3 -- F06's title block has a Korean
  ATTRIB value (`2층 구조평면도`) that acad-ts mis-decodes, so the *string* hashed differs even
  though the algorithm and the rest of the text set are correct. Every other measure
  (`count_by_type`, `entity_count`, `length_sum_mm`, `hatch_area_sum_mm2`, `text_count`) matches
  `fixtures/truth/F06.json` exactly. Not part of the brief's named acceptance fields
  (`count_by_type`/`length_sum`/`hatch_area_sum`/`insert_by_block`).
- `length_sum_mm` includes ELLIPSE, per `stats-definition.md`'s field table (LINE, LWPOLYLINE,
  POLYLINE(2D), ARC, CIRCLE, ELLIPSE, SPLINE) -- `fixtures/gen`'s own truth-computation
  (`LENGTH_TYPES` in `fixtures/gen/src/fixtures_gen/stats.py`) omits ELLIPSE, a leftover from the
  W1-03 brief's older Inputs list. F01 is the only fixture with ELLIPSE entities.

## Round-trip results (DXF -> DWG -> DXF or DXF -> DWG, F01-F10)

`count_by_type`, `length_sum_mm`, `hatch_area_sum_mm2`, `text_count`, `insert_by_block` compared
before/after with acad-ts's own `stats`, on every one of F01-F09 plus F10_host/F10_grid:

| Fixture | Result |
|---|---|
| F01, F02, F03, F04, F05, F07, F08, F09, F10_host | **Exact match.** F02 additionally checked: entity handles survive DXF->DWG->DXF unchanged, in order (`roundtrip.test.ts`). |
| F06, F10_grid | **`insert_by_block` and `count_by_type.INSERT` off by exactly one** -- the `X-TITLE` INSERT (Known gap #1). Everything else (`length_sum_mm`, `hatch_area_sum_mm2`, every other bucket) matches exactly. Regression-tested in `roundtrip.test.ts`'s `describe("known gap: ...")`. |

ezdxf/mlightcad crosscheck (ADR-0002 6) is out of scope for this task -- **W2-04 (engine ezdxf
stats.py) still needs to cross-validate against this package's `stats` output** on the same
fixtures, per the brief.

## Files

```
src/cli.ts                    CLI entry (argv dispatch)
src/commands/*.ts              dwg2dxf / dxf2dwg / stats / info
src/acad/read.ts, write.ts     acad-ts reader/writer wrappers (keepUnknownEntities, notification capture)
src/acad/walk.ts               (space, entity) iteration incl. INSERT.attributes, SeqendCollection guard
src/acad/entity-types.ts       DXF type name -> LayerStatsDocument entity_type enum
src/acad/length.ts             length_sum_mm (bulge analytic formula; SPLINE/ELLIPSE flattened via acad-ts's polygonalVertexes)
src/acad/hatch-area.ts         hatch_area_sum_mm2 (signed shoelace, external/outermost vs. hole)
src/acad/text.ts               text_hash (NFC, code-point sort, sha1)
src/acad/stats-builder.ts      LayerStatsDocument bucket/totals assembly
src/acad/scan-unsupported.ts   drop detection for dwg2dxf/dxf2dwg (no full stats build)
src/drops.ts                   *.drops.json shape and sidecar path
src/acad/version.ts            ACadVersion name parsing
```
