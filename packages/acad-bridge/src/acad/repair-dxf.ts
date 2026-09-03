import { AttributeBase, type CadDocument } from "@node-projects/acad-ts";

import { walkSpaceEntities } from "./walk";

/**
 * Post-processes the raw DXF text {@link DxfWriter.writeToStream} produced
 * (`write.ts`'s `writeDxfFile`), fixing three real acad-ts DXF *writer*
 * defects found while implementing this bridge (brief W3-08 goal 3, G0
 * follow-up 3) -- pure text -> text, acad-ts is never forked or
 * monkey-patched (brief Constraints: "acad-ts 포크 금지"). Each fix is
 * isolated with a minimal reproduction against the acad-ts source
 * (`node_modules/@node-projects/acad-ts/dist/IO/DXF/DxfStreamWriter/DxfSectionWriterBase.js`),
 * not just observed once in a fixture -- see each function's docstring.
 *
 * All three were found on `fixtures/generated/F06.dwg` -> `dwg2dxf` (the
 * duplicate SEQEND and missing ATTRIB subclass) and `F03.dwg` -> `dwg2dxf`
 * (the zero-length MTEXT direction vector); `engine/src/halo_engine/ingest/
 * stats.py`'s module docstring documents the crashes these cause downstream
 * when *not* repaired (W3-08 goal 1's diagnostics are the fallback for a
 * caller that skips this repair, e.g. `stats`ing an `.acad.dxf` this
 * package did not just write).
 */

// ---------------------------------------------------------------------------
// Generic raw-DXF-text record helpers. Deliberately narrow: only what the
// three fixes below need, not a general DXF text parser.
// ---------------------------------------------------------------------------

interface TopLevelRecord {
  /** DXF entity/table/section type name, e.g. "ATTRIB", "MTEXT", "SEQEND". */
  type: string;
  /** Index of the `\n` right before this record's `  0` group-0 line. */
  start: number;
  /** Index where this record ends: the next record's `start`, or `text.length`. */
  end: number;
}

/**
 * Group-0 ("entity/section start") lines are always written `  0\n<NAME>\n`
 * by both ezdxf and every DXF this package's writer produces (`DxfCode.Start`
 * -- ASCII DXF group codes are right-justified to a 3-character field, see
 * {@link groupCodeLinePrefix}), so this narrow pattern is reliable for the
 * writer output this module repairs -- it is not a general-purpose DXF
 * tokenizer.
 */
const TOP_LEVEL_RECORD_RE = /(?:^|\n) {2}0\n([A-Za-z_][A-Za-z0-9_]*)\n/g;

function findTopLevelRecords(text: string): TopLevelRecord[] {
  const starts: { index: number; type: string }[] = [];
  TOP_LEVEL_RECORD_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TOP_LEVEL_RECORD_RE.exec(text)) !== null) {
    const type = match[1];
    if (type === undefined) continue; // capture group is mandatory in the pattern; defensive only
    starts.push({ index: match.index, type });
  }
  return starts.map((entry, i) => {
    const next = starts[i + 1];
    return { type: entry.type, start: entry.index, end: next === undefined ? text.length : next.index };
  });
}

/** ASCII DXF group codes are right-justified to width 3, e.g. `"  0"`, `"  5"`, `" 11"`, `"330"`. */
function groupCodeLinePrefix(code: number): string {
  return String(code).padStart(3, " ");
}

/** The value on the line after the first `\n<code>\n` inside `span`, or `null` if absent. */
function firstGroupValue(span: string, code: number): string | null {
  const marker = `\n${groupCodeLinePrefix(code)}\n`;
  const idx = span.indexOf(marker);
  if (idx === -1) return null;
  const valueStart = idx + marker.length;
  const valueEnd = span.indexOf("\n", valueStart);
  return valueEnd === -1 ? null : span.slice(valueStart, valueEnd);
}

/**
 * `record.end` is the position where the *next* record's leading `\n`
 * begins, so a plain `text.slice(record.start, record.end)` drops that one
 * shared byte -- invisible for a code that has more fields after it (every
 * real fixture this module has been tested against), but it means
 * {@link firstGroupValue} finds no closing `\n` (so returns `null`) when the
 * queried code happens to be the last field before the next record, e.g. a
 * bare `LINE` whose handle (group 5) is its final field. Reading one byte
 * past `record.end` recovers that shared newline; safe by construction, it
 * can never accidentally reach into the *next* record's own fields.
 */
function recordValueSpan(text: string, record: TopLevelRecord): string {
  return text.slice(record.start, Math.min(record.end + 1, text.length));
}

function applyEdits(
  text: string,
  edits: readonly { start: number; end: number; replacement: string }[]
): string {
  // Apply from the end so earlier positions stay valid across replacements
  // of different lengths.
  let result = text;
  for (const { start, end, replacement } of [...edits].sort((a, b) => b.start - a.start)) {
    result = result.slice(0, start) + replacement + result.slice(end);
  }
  return result;
}

function isNumericZero(value: string | null): boolean {
  if (value === null) return false;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) && Math.abs(n) < 1e-9;
}

// ---------------------------------------------------------------------------
// Fix 1: a SEQEND written twice for the same INSERT, with the identical
// handle both times (acad-bridge README "Known acad-ts gaps" #2).
// ---------------------------------------------------------------------------

/**
 * `DxfSectionWriterBase._writeInsert` (acad-ts source, see module docstring
 * for the path):
 *
 * ```js
 * for (const att of insert.attributes) { this.writeEntity(att); }
 * if (insert.hasAttributes && insert.attributes.seqend) {
 *   this.writeEntity(insert.attributes.seqend);
 * }
 * ```
 *
 * `insert.attributes` (a `SeqendCollection`) can contain the terminating
 * SEQEND as a plain element too, not only via the separate `.seqend`
 * property the code above trusts (the same runtime shape gap `walk.ts`
 * already guards on read, README gap #2) -- when it does, the loop's
 * `this.writeEntity(att)` writes that SEQEND once, and the explicit
 * `this.writeEntity(insert.attributes.seqend)` right after writes the exact
 * same object again: two byte-identical `SEQEND` records, same handle,
 * immediately adjacent. ezdxf's `Drawing.audit()` resolves the resulting
 * duplicate handle by destroying whichever entity is no longer the entity
 * database's canonical entry for it -- but the destroyed object is still
 * referenced by its owning INSERT's `attribs`, so touching it later raises
 * (`halo_engine.ingest.stats`'s `dead-attrib` diagnostic guards exactly this
 * when it is *not* repaired first).
 *
 * Removing the redundant second copy is a deletion, not a "give it a new
 * handle" reassignment (brief wording: "중복 핸들 재부여") -- because the
 * two records are not two different entities that happen to collide, they
 * are the *same* logical SEQEND serialized twice; minting the copy a new
 * handle would leave two terminators for one INSERT, which is invalid
 * either way. {@link reassignRemainingDuplicateHandles} below is the
 * general reassignment fallback for a handle collision that is *not* this
 * exact duplicate-block shape (none observed in F01-F10, but the fixes stay
 * independent so one only ever discards what it has proven is redundant).
 */
function dedupeDuplicateSeqend(text: string): { text: string; count: number } {
  const records = findTopLevelRecords(text);
  const edits: { start: number; end: number; replacement: string }[] = [];
  for (let i = 0; i < records.length - 1; i++) {
    const a = records[i];
    const b = records[i + 1];
    if (a === undefined || b === undefined) continue; // unreachable given the loop bound
    if (a.type !== "SEQEND" || b.type !== "SEQEND") continue;
    if (text.slice(a.start, a.end) !== text.slice(b.start, b.end)) continue;
    edits.push({ start: b.start, end: b.end, replacement: "" });
  }
  return { text: applyEdits(text, edits), count: edits.length };
}

// ---------------------------------------------------------------------------
// Fix 2: ATTRIB missing its "AcDbAttribute" subclass marker and tag (group 2).
// ---------------------------------------------------------------------------

/**
 * `AttributeEntity extends AttributeBase extends TextEntity`, but
 * `DxfSectionWriterBase.writeEntity`'s `instanceof` dispatch chain (acad-ts
 * source, see module docstring for the path) has a branch for
 * `entity instanceof TextEntity` and none for `AttributeBase`/
 * `AttributeEntity` above it, so every ATTRIB falls into the generic
 * `_writeTextEntity` branch -- the ATTRIB-specific `_writeAttributeBase`
 * method exists in the same file and correctly writes `AcDbAttribute` /
 * `tag` / `flags` / ..., but is never called from anywhere. Compounding
 * this, `_writeTextEntity` itself writes its own subclass marker *twice*
 * (`this._writer.write(DxfCode.Subclass, DxfSubclassMarker.text)` appears
 * both at the top of the method and again right before the final `73`
 * field -- harmless duplication for a plain TEXT, but for an ATTRIB it
 * leaves a second, empty `AcDbText` marker exactly where `AcDbAttribute`
 * belongs and no `tag` (group 2) anywhere in the record.
 *
 * ezdxf's own `Attrib.audit()` deletes any ATTRIB without a `tag`
 * (`ezdxf/entities/attrib.py`: `if not self.dxf.hasattr("tag"):
 * auditor.trash(self)`) -- confirmed empirically: the *only* thing standing
 * between a de-duplicated (see {@link dedupeDuplicateSeqend}) but otherwise
 * unrepaired ATTRIB and `ezdxf.readfile(...).audit()` destroying it anyway
 * is this missing tag, even though every other field (value, layer, geometry)
 * already reads correctly without it.
 *
 * The fix renames that redundant second `AcDbText` marker to `AcDbAttribute`
 * and inserts the tag, read from the in-memory `CadDocument` (`att.tag`,
 * `AttributeBase`'s real, correctly-populated property -- this bug is
 * writer-only) and matched to the DXF record by handle. An ATTRIB whose
 * handle is not found in `doc` (should not happen; defensive) is left
 * untouched rather than guessed at.
 */
function restoreAttributeSubclass(
  text: string,
  doc: CadDocument
): { text: string; count: number } {
  const tagByHandle = new Map<string, string>();
  for (const { entity } of walkSpaceEntities(doc)) {
    if (entity instanceof AttributeBase) {
      tagByHandle.set(entity.handle.toString(16).toUpperCase(), entity.tag);
    }
  }
  if (tagByHandle.size === 0) return { text, count: 0 };

  const records = findTopLevelRecords(text);
  const edits: { start: number; end: number; replacement: string }[] = [];
  const marker = "\n100\nAcDbText\n";
  for (const record of records) {
    if (record.type !== "ATTRIB") continue;
    const span = recordValueSpan(text, record);
    const handle = firstGroupValue(span, 5);
    if (handle === null) continue;
    const tag = tagByHandle.get(handle);
    if (tag === undefined) continue;
    const firstIdx = span.indexOf(marker);
    if (firstIdx === -1) continue;
    const secondIdx = span.indexOf(marker, firstIdx + marker.length);
    if (secondIdx === -1) continue; // not the shape this fix recognises -- leave alone
    edits.push({
      start: record.start + secondIdx,
      end: record.start + secondIdx + marker.length,
      replacement: `\n100\nAcDbAttribute\n  2\n${tag}\n`,
    });
  }
  return { text: applyEdits(text, edits), count: edits.length };
}

// ---------------------------------------------------------------------------
// Fix 3: a zero-length MTEXT x-axis direction vector (group 11/21/31).
// ---------------------------------------------------------------------------

/**
 * `DxfSectionWriterBase._writeMText` unconditionally writes
 * `this._writer.writeVector(11, mtext.alignmentPoint, subclass)` -- group
 * 11/21/31 is DXF's MTEXT "X-axis direction vector (in WCS)"
 * (`ezdxf.entities.mtext`'s `text_direction`), but acad-ts's own model calls
 * the same field `alignmentPoint` and defaults it to the zero vector when a
 * source file (such as an ezdxf-written MTEXT with no direction override)
 * never sets it, rather than defaulting to the X axis. ezdxf loads MTEXT's
 * `text_direction` through `fast_load_dxfattribs`, which bypasses the
 * validator (`is_not_null_vector`/`fixer=RETURN_DEFAULT`) that would
 * otherwise catch this on the read side, so the zero vector survives into
 * the document and `ezdxf.bbox.extents()` crashes building an OCS/UCS from
 * it (`ZeroDivisionError` -- `halo_engine.ingest.stats`'s module docstring
 * has the full call chain; its `zero-length-ocs-vector` diagnostic guards
 * exactly this when it is *not* repaired first).
 *
 * The fix replaces a `(0, 0, 0)` group 11/21/31 with `(1, 0, 0)`, ezdxf's
 * own default ("normalizes" the vector to a valid unit vector, matching the
 * brief's "MTEXT x축 벡터 정규화"). Any non-zero direction -- the ordinary
 * case -- is left exactly as acad-ts wrote it.
 */
function normalizeZeroLengthMTextDirection(text: string): { text: string; count: number } {
  const records = findTopLevelRecords(text);
  const edits: { start: number; end: number; replacement: string }[] = [];
  for (const record of records) {
    if (record.type !== "MTEXT") continue;
    const span = recordValueSpan(text, record);
    const x = firstGroupValue(span, 11);
    const y = firstGroupValue(span, 21);
    const z = firstGroupValue(span, 31);
    if (x === null || !isNumericZero(x) || !isNumericZero(y) || !isNumericZero(z)) continue;
    const marker = `\n 11\n${x}\n`;
    const idx = span.indexOf(marker);
    if (idx === -1) continue;
    edits.push({
      start: record.start + idx,
      end: record.start + idx + marker.length,
      replacement: "\n 11\n1\n",
    });
  }
  return { text: applyEdits(text, edits), count: edits.length };
}

// ---------------------------------------------------------------------------
// Fix 4 (general safety net): any handle collision the specific fixes above
// did not already resolve.
// ---------------------------------------------------------------------------

/**
 * Runs last, after {@link dedupeDuplicateSeqend} has already removed the one
 * duplicate-handle shape this package has evidence for. A handle that still
 * collides at this point is, by construction, not that shape (two identical
 * records) -- reassigning it a fresh handle preserves both entities' data
 * rather than guessing which one to discard. No fixture in F01-F10 reaches
 * this path once the other three fixes have run; it exists so a future,
 * different acad-ts writer bug degrades to a still-readable file instead of
 * ezdxf's audit silently destroying an entity again.
 */
function reassignRemainingDuplicateHandles(text: string): { text: string; count: number } {
  const records = findTopLevelRecords(text);
  let maxHandle = 0;
  for (const record of records) {
    const handle = firstGroupValue(recordValueSpan(text, record), 5);
    if (handle === null) continue;
    const parsed = Number.parseInt(handle, 16);
    if (Number.isFinite(parsed) && parsed > maxHandle) maxHandle = parsed;
  }

  const seen = new Set<string>();
  const edits: { start: number; end: number; replacement: string }[] = [];
  let nextHandle = maxHandle + 1;
  for (const record of records) {
    const span = recordValueSpan(text, record);
    const handle = firstGroupValue(span, 5);
    if (handle === null) continue;
    if (!seen.has(handle)) {
      seen.add(handle);
      continue;
    }
    const marker = `\n  5\n${handle}\n`;
    const idx = span.indexOf(marker);
    if (idx === -1) continue;
    const freshHandle = (nextHandle++).toString(16).toUpperCase();
    edits.push({
      start: record.start + idx,
      end: record.start + idx + marker.length,
      replacement: `\n  5\n${freshHandle}\n`,
    });
  }
  return { text: applyEdits(text, edits), count: edits.length };
}

// ---------------------------------------------------------------------------

export interface DxfRepairResult {
  text: string;
  duplicateSeqendRemoved: number;
  attributeSubclassRestored: number;
  mtextDirectionNormalized: number;
  remainingDuplicateHandlesReassigned: number;
}

/**
 * Repairs the raw DXF text a {@link DxfWriter} produced for `doc`, in the
 * order each fix's own docstring assumes: SEQEND de-duplication first (it
 * is what makes the later handle-collision safety net's baseline correct),
 * then the two independent, per-record content fixes, then the general
 * safety net last.
 */
export function repairDxfText(text: string, doc: CadDocument): DxfRepairResult {
  const seqend = dedupeDuplicateSeqend(text);
  const attribute = restoreAttributeSubclass(seqend.text, doc);
  const mtext = normalizeZeroLengthMTextDirection(attribute.text);
  const handles = reassignRemainingDuplicateHandles(mtext.text);
  return {
    text: handles.text,
    duplicateSeqendRemoved: seqend.count,
    attributeSubclassRestored: attribute.count,
    mtextDirectionNormalized: mtext.count,
    remainingDuplicateHandlesReassigned: handles.count,
  };
}
