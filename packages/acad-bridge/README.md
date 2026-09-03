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
| Non-ASCII (Korean) text decoding, any DXF/DWG version | **Broken in acad-ts, worked around here** | See "Known acad-ts gaps" #3 -- `acad/decode-fix.ts` fixes it in this package's read path; `stats` `text_hash` matches ezdxf truth exactly. |
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
3. **acad-ts decodes all DXF/DWG text bytes as windows-1252, regardless of the file's real
   encoding -- worked around in `acad/decode-fix.ts`.** Originally found on
   `F03_r2000_cp949.dxf` (R2000, `$DWGCODEPAGE` = `ANSI_949`; ezdxf itself round-trips this file's
   cp949 correctly per `fixtures/gen/tests/test_cp949_roundtrip.py`), where TEXT read back as e.g.
   `°Å½Ç` for source `거실` ("living room"). The *same* corruption showed up reading the
   **primary R2018/AC1032 UTF-8 fixtures directly** too (`F03.dxf`'s TEXT values came back
   `"ê±°ì‹¤"`, `"ì¹¨ì‹¤1"`, ...) -- so it is not a legacy-codepage-only bug: acad-ts always decodes
   multi-byte text as windows-1252, even for R2007+/UTF-8-era files where DXF text is UTF-8 bytes
   directly.

   This turned out to be reversible without forking acad-ts, because acad-ts's windows-1252
   decode is precise and byte-preserving *except* for the 5 code points CP1252 itself leaves
   undefined (`0x81`, `0x8D`, `0x8F`, `0x90`, `0x9D`), where acad-ts passes the byte value through
   directly (confirmed with a synthetic round trip: a `TextEntity("적")` -- UTF-8 bytes
   `EC A0 81` -- written and reread comes back with code points `ec a0 81`, i.e. the last byte
   passed straight through rather than becoming U+FFFD or CP1252's `?`). `acad/decode-fix.ts`
   reverses this precisely (a 32-entry table for CP1252's `0x80-0x9F` block, including those 5
   as identity, everything else Latin-1-identity) to recover the *original bytes*, then decodes
   those bytes with the real target encoding: UTF-8 for `$ACADVER` AC1021+ (R2007+), else the
   `iconv-lite` (MIT) encoding for `$DWGCODEPAGE` (e.g. `ANSI_949` -> `cp949`). Naively reversing
   via `iconv-lite`'s own windows-1252 *encoder* does not work for this: it maps all 5 of those
   code points to `?`, which is why this package needed its own table rather than a plain
   `iconv.encode(s, "windows-1252")` round trip.

   Applied unconditionally to every TEXT/MTEXT/ATTRIB/ATTDEF value, layer name, and block name
   read by `read.ts` (both `readDxfFile` and `readDwgFile` -- the DWG read path showed the same
   pattern). Safe by construction: when the *correct* target encoding is windows-1252 itself
   (the common case for fixtures without Korean text), reversing and redecoding through
   windows-1252 is the identity, so nothing changes; and if the fixed string would contain a
   replacement character, the original is kept instead (never make already-plausible text worse).
   `src/acad/encoding-fix.test.ts` checks the fix directly against `fixtures/truth/F03.json` /
   `F06.json`'s `text_hash` (computed independently by ezdxf, W2-03) -- **exact match**, on
   `F03.dxf` (UTF-8), `F03_r2000_cp949.dxf` (legacy cp949), `F03.dxf` -> DWG -> `stats`, and
   `F06.dxf` (whose title block carries the Korean ATTRIB `2층 구조평면도`).
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
5. **`DxfSectionWriterBase.writeEntity`'s `instanceof` dispatch chain never routes an ATTRIB to
   `_writeAttributeBase`.** `AttributeEntity extends AttributeBase extends TextEntity`, and the
   dispatch chain (`node_modules/@node-projects/acad-ts/dist/IO/DXF/DxfStreamWriter/DxfSectionWriterBase.js`)
   has a branch for `entity instanceof TextEntity` and none for `AttributeBase`/`AttributeEntity`
   above it in the chain -- so every ATTRIB falls into the generic `_writeTextEntity` branch.
   `_writeAttributeBase` (same file) exists, correctly writes the `AcDbAttribute` subclass, `tag`
   (group 2), `flags`, etc., and is never called from anywhere. Compounding this,
   `_writeTextEntity` itself writes its own subclass marker (`100`/`AcDbText`) *twice* -- once at
   the top of the method, once again right before its final field (group 73) -- harmless
   duplication for a plain TEXT entity, but for an ATTRIB it leaves an empty, wrongly-named second
   `AcDbText` marker exactly where `AcDbAttribute` belongs, and no tag anywhere in the record.
   ezdxf's own `Attrib.audit()` deletes any ATTRIB without a tag
   (`ezdxf/entities/attrib.py`: `if not self.dxf.hasattr("tag"): auditor.trash(self)`) -- confirmed
   empirically on `fixtures/generated/F06.dwg` -> `dwg2dxf`: every other field (value, layer,
   geometry) reads correctly from the malformed record, but `ezdxf.readfile(...).audit()` destroys
   the entity anyway purely because the tag is missing. Repaired in `repair-dxf.ts`'s
   `restoreAttributeSubclass` -- see "DXF writer repair" below.
6. **`insert.attributes` can independently contain the terminating SEQEND (gap #2), and `_writeInsert`
   writes it twice when it does.** `_writeInsert`: `for (const att of insert.attributes) {
   this.writeEntity(att); } if (insert.hasAttributes && insert.attributes.seqend) {
   this.writeEntity(insert.attributes.seqend); }` -- when gap #2's runtime shape (the SEQEND present
   as a plain element of `insert.attributes`, not only via the separate `.seqend` property) applies,
   the loop's `writeEntity(att)` call writes that SEQEND once, and the explicit call right after
   writes the *same object* again: two byte-identical `SEQEND` records, same handle, immediately
   adjacent. ezdxf's `Drawing.audit()` resolves the resulting duplicate handle by destroying
   whichever entity is no longer the entity database's canonical entry for it, which is silent (no
   `auditor.errors` entry -- only a `logger.warning("Found non-unique entity handle #...")` during
   the earlier bind step) and, because the destroyed object is still referenced by its owning
   INSERT's `attribs`, crashes any later code that touches it
   (`engine/src/halo_engine/ingest/stats.py`'s `dead-attrib` diagnostic guards exactly this when it
   is *not* repaired first). Repaired in `repair-dxf.ts`'s `dedupeDuplicateSeqend`.
7. **MTEXT's `alignmentPoint` (DXF group 11/21/31, the X-axis direction vector) defaults to the
   zero vector, and `_writeMText` writes it unconditionally.** A source MTEXT with no explicit
   direction override (the ordinary case; ezdxf itself omits group 11 entirely rather than writing
   a default) reads back into acad-ts's model with `alignmentPoint` at its zero-vector default
   rather than the X axis, and `_writeMText`'s `this._writer.writeVector(11, mtext.alignmentPoint,
   subclass)` serializes that default faithfully. ezdxf loads MTEXT's `text_direction` through
   `fast_load_dxfattribs`, which bypasses the validator (`is_not_null_vector`/
   `fixer=RETURN_DEFAULT`) that would otherwise catch this on read, so the zero vector survives
   into the document and `ezdxf.bbox.extents()` crashes building an OCS/UCS from it
   (`ZeroDivisionError` inside `ezdxf.math.OCS.__init__`'s `Vec3(extrusion).normalize()`) --
   confirmed on `fixtures/generated/F03.dwg` -> `dwg2dxf`, all 10 MTEXT entities.
   `engine/src/halo_engine/ingest/stats.py`'s `zero-length-ocs-vector` diagnostic guards this when
   it is *not* repaired first. Repaired in `repair-dxf.ts`'s `normalizeZeroLengthMTextDirection`
   (replaces the zero vector with `(1, 0, 0)`, ezdxf's own default -- "normalizes" it, per the
   brief's own wording).
8. **`AttributeBase.tag` is never populated on read, from any source (DWG or DXF, well-formed or
   not).** `_tag` defaults to `''` (`Entities/AttributeBase.js`) and no code path in the DXF reader
   (`IO/DXF/DxfStreamReader/DxfSectionReaderBase.js`'s `_readAttributeDefinition`) or the DWG reader
   ever assigns `.tag` from group 2 -- confirmed by reading `fixtures/generated/F06.dxf` directly
   (bypassing this package's writer entirely): every ATTRIB's `tag` comes back `''` even though the
   file's `AcDbAttribute` subclass and group 2 are perfectly well formed. This means gap #5's repair
   (`restoreAttributeSubclass`) can restore the `AcDbAttribute` subclass structure -- which is what
   stops ezdxf's audit from deleting the entity -- but cannot recover the *tag string itself*, since
   the in-memory `CadDocument` this package repairs from never had it to begin with. Harmless for
   this task's purposes (`stats-definition.md`'s measures never read an ATTRIB's tag, only its
   value and layer, both unaffected), but worth knowing before relying on `AttributeBase.tag` for
   anything else.

## DXF writer repair (`repair-dxf.ts`)

Every `writeDxfFile` call (`dwg2dxf`, `dxf2dwg`'s round-trip tests, `stats` on a freshly-converted
file) post-processes the raw DXF text `DxfWriter.writeToStream` produced before it reaches disk --
pure text -> text, acad-ts itself is never forked or monkey-patched (brief W3-08 Constraints).
Fixes gaps #5-#7 above:

| Fix | Gap | What it does |
|---|---|---|
| `dedupeDuplicateSeqend` | #6 | Removes the second of two byte-identical, adjacent `SEQEND` records. |
| `restoreAttributeSubclass` | #5 | Renames ATTRIB's erroneous second `AcDbText` marker to `AcDbAttribute` and inserts a tag (group 2), read from the in-memory `CadDocument` by handle -- empty per gap #8, but present, which is what matters to ezdxf's audit. |
| `normalizeZeroLengthMTextDirection` | #7 | Replaces a `(0, 0, 0)` MTEXT direction vector (group 11/21/31) with `(1, 0, 0)`. |
| `reassignRemainingDuplicateHandles` | general safety net | Mints a fresh handle for any handle collision the three fixes above did not already resolve (none observed in F01-F10 once they have run; guards a *different*, not-yet-seen acad-ts writer bug producing the same symptom). |

Verified end to end against `fixtures/generated/F06.dwg` and `F03.dwg`: `engine ingest.stats`
(Python/ezdxf) reads the repaired output without exception, and F06's `stats` output matches
`fixtures/truth/F06.json` exactly except for the `INSERT`/`insert_by_block` count for `X-TITLE`
(gap #1, unrelated to and not fixed by this repair) -- `count_by_type`, `length_sum_mm`,
`hatch_area_sum_mm2`, and every `X-GRID` ATTRIB's `text_count` contribution match. F03's `stats`
output (`count_by_type`, `bbox`, `text_hash`) matches `fixtures/truth/F03.json` exactly.
`repair-dxf.test.ts` covers each fix in isolation (synthetic DXF text) and the two real fixtures
end to end.

## `stats`: schema and contract notes

- `producer` is the schema's `{name, version}` object (`packages/schema/src/ndj/document.schema.json#/$defs/producer`),
  not the bare string `"acad-ts"` docs/contracts/stats-definition.md's prose describes -- the
  schema is what `validateLayerStats` actually checks, and is treated as authoritative wherever the
  two disagree (see this task's report "Deviations from brief" for every such case).
- `count_by_type`'s keys are **raw DXF record names** (`entity.objectName`, e.g. `MULTILEADER`,
  not `MLEADER`) matching `^[A-Z][A-Z0-9_]*$`, per
  `packages/schema/src/stats/layer-stats.schema.json#/$defs/count_by_type` and the post-merge
  contract note ("통합에서 확정된 사항 ... count_by_type 키는 raw DXF 레코드명이다"). This is a
  *different*, looser constraint from the closed `entity_type` enum used by NDJ documents
  (`packages/schema/src/ndj/entity.schema.json`), which does still use `MLEADER` -- irrelevant to
  `stats` output. The one remaining semantic rename is `DimensionArc`'s DXF subclass token
  `ARC_DIMENSION` -> `DIMENSION` (stats-definition.md: "DIMENSION 하위 유형은 모두 DIMENSION").
  Anything whose raw name does not fit the key pattern at all (observed: none in F01-F10; `3DFACE`/
  `3DSOLID` would not, since they start with a digit) is excluded from `stats` output and recorded
  as a `stats-schema-unsupported-type` drop.
- `count_by_type`/`entity_count` exclude ATTRIB (`stats-definition.md`: "ATTRIB·SEQEND·VERTEX는
  세지 않는다(소유 엔티티에 속함)"); ATTRIB still contributes to `text_count`/`text_hash` under its
  *own* layer's bucket. Confirmed against `fixtures/truth/F06.json` (post-merge, now a real
  `LayerStatsDocument`): `entity_count: 86`, `text_count: 40` (30 TEXT + 10 ATTRIB), no `ATTRIB` key
  in `count_by_type` -- all three match this package's output on `F06.dxf` exactly.
- `text_hash` on F06 now matches `fixtures/truth/F06.json` exactly (`125bac30a2dbb6b8`), once
  read through the windows-1252 decode workaround ("Known acad-ts gaps" #3): F06's title block has
  a Korean ATTRIB value (`2층 구조평면도`) that acad-ts otherwise mis-decodes, changing the string
  hashed even though the algorithm (confirmed identical to `fixtures/gen/src/fixtures_gen/stats.py`'s
  `_text_hash`/`_nfc_sorted_join`, W2-03's updated implementation) was always correct.
- `length_sum_mm` includes ELLIPSE, per `stats-definition.md`'s field table (LINE, LWPOLYLINE,
  POLYLINE(2D), ARC, CIRCLE, ELLIPSE, SPLINE). `fixtures/truth/F01.json` (post-merge, now
  computed by the same contract) agrees it should be included -- `count_by_type` there lists
  `ELLIPSE: 2` and F01 is the only fixture with ELLIPSE entities either way -- but the actual
  **value** differs by about 0.5% (this package: `50449.687945`; truth: `50714.822632`), outside
  the ±0.1% crosscheck tolerance. F01 also has 2 SPLINE entities; neither ELLIPSE nor SPLINE has an
  exact closed-form length, so both parsers are approximating a curve by flattening it at a chosen
  precision, and the two precisions do not agree closely enough. This is the same class of gap the
  contract already flags as a whitelist candidate for the mlightcad side ("mlightcad 스플라인 길이는
  flattening(0.01)급이 아니어서 F01에서 ezdxf 대비 약 11% 크다") -- W2-04/G1 should decide whether
  acad-ts's curve length also needs a whitelist entry, or whether `acad/length.ts`'s flattening
  precision (`flatteningPrecision` in that file) should be tightened.

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
src/acad/decode-fix.ts         windows-1252-forced-decode workaround (see "Known acad-ts gaps" #3)
src/acad/repair-dxf.ts         DXF writer output repair: duplicate SEQEND, ATTRIB subclass, MTEXT direction (see "Known acad-ts gaps" #5-#7, "DXF writer repair")
src/acad/walk.ts               (space, entity) iteration incl. INSERT.attributes, SeqendCollection guard
src/acad/entity-types.ts       raw DXF record name -> count_by_type key (DimensionArc normalisation, key-pattern guard)
src/acad/length.ts             length_sum_mm (bulge analytic formula; SPLINE/ELLIPSE flattened via acad-ts's polygonalVertexes)
src/acad/hatch-area.ts         hatch_area_sum_mm2 (signed shoelace, external/outermost vs. hole)
src/acad/text.ts               text_hash (NFC, code-point sort, sha1)
src/acad/stats-builder.ts      LayerStatsDocument bucket/totals assembly
src/acad/scan-unsupported.ts   drop detection for dwg2dxf/dxf2dwg (no full stats build)
src/drops.ts                   *.drops.json shape and sidecar path
src/acad/version.ts            ACadVersion name parsing
```
