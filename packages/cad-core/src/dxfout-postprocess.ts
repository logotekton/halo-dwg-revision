/**
 * Repairs the two group codes `AcDbDatabase.dxfOut()` leaves out.
 *
 * ADR-0002 (개정 2026-09-02 §3) makes `dxfOut()` the default DWG→DXF converter
 * and lists exactly two defects, both measured in `docs/spikes/large-file.md`
 * §4.2 and both re-measured here on `fixtures/generated/F06.dxf`:
 *
 * 1. **INSERT is missing group `66` ("attributes follow").** The ATTRIB records
 *    themselves are complete and correctly ordered (`INSERT ATTRIB … SEQEND`)
 *    with owner group `330` pointing at the INSERT, but without `66 1` ezdxf's
 *    `EntityLinker` refuses to attach them: F06 loses 10 of 40 `text_count` and
 *    grows 8 orphan SEQENDs as top-level entities (`entity_count` 94 ≠ 86).
 * 2. **HATCH boundary paths lose the External bit of group `92`** (`3` →`2`),
 *    which flips the sign of the signed boundary area: −4 320 000 instead of
 *    +4 320 000 mm² on F06.
 *
 * Three more came out of W3-09's measurement over the real drawing set, where
 * the engine could read only 26 of 68 `dxfOut()` results
 * (`docs/spikes/real-dwg-measurement.md`):
 *
 * 3. **LEADER (and DIMENSION) records name a dimension style `0`** that the
 *    DIMSTYLE table does not contain. `ezdxf.bbox` builds a `DimStyleOverride`
 *    per leader and raises `DXFTableEntryError: 0` — the single cause of the
 *    42 unreadable files. The name is restored to the drawing's `$DIMSTYLE`,
 *    or `Standard`, or the first style the table does define.
 * 4. **STYLE records write the big-font name as `0`** instead of empty
 *    (811 of 838 styles). `0` is not a font file, and a reader that resolves
 *    it looks for one.
 * 5. **Handles repeat.** Every later occurrence is re-issued above
 *    `$HANDSEED`, and `$HANDSEED` is bumped past the highest handle in use.
 *
 * The contract for this module (brief W3-02, Constraints) is narrow: *only*
 * those two things change and **no other byte moves**. It is therefore written
 * as a line-pair rewrite over the DXF text — no parse, no re-serialisation —
 * and every transformation is reported in {@link DxfPostProcessResult} so the
 * caller can log what it did.
 *
 * Pure string work, no mlightcad import: it runs in the hidden converter
 * window, in the desktop main process and in vitest alike.
 */

/** Counters describing what {@link postProcessDxfOut} changed. */
export interface DxfPostProcessReport {
  /** INSERT records that received `66 1`. */
  insertsFlagged: number;
  /** INSERTs that already carried a correct `66`; left untouched. */
  insertsAlreadyFlagged: number;
  /** HATCH boundary paths whose group 92 gained the External bit. */
  hatchLoopsFlagged: number;
  /** HATCH records seen. */
  hatchCount: number;
  /** LEADER/DIMENSION records re-pointed at an existing dimension style. */
  dimStylesRestored: number;
  /** STYLE records whose big-font name was the literal `0`. */
  bigFontsCleared: number;
  /** Records whose handle collided with an earlier one and was re-issued. */
  handlesReassigned: number;
  /** Line ending detected in the input, reused verbatim for inserted lines. */
  lineEnding: '\r\n' | '\n';
}

export interface DxfPostProcessResult extends DxfPostProcessReport {
  text: string;
  /** True when nothing had to change (the input was already conformant). */
  unchanged: boolean;
}

/** DXF group 3 of LEADER/DIMENSION: the dimension style name. */
const DIMSTYLE_NAME_CODE = 3;
/** DXF group 4 of STYLE: the big-font file name. */
const BIGFONT_CODE = 4;
/** The value `dxfOut()` writes where a name is unknown. */
const UNKNOWN_NAME = '0';
const HANDLE_REPAIR_BISECT = false;

/** Bit 0 of DXF group 92: this boundary path is an external boundary. */
const EXTERNAL_BIT = 1;
/** Bit 4 of DXF group 92: outermost boundary; ezdxf accepts either as "adds area". */
const OUTERMOST_BIT = 16;

/**
 * The file as group code / value pairs.
 *
 * Codes live in an `Int32Array` and values are read back out of `lines` — pair
 * *i* is always lines `2i` (code) and `2i + 1` (value), so no per-pair object
 * is allocated. That matters at real-drawing scale: a 10 MB DWG converts to a
 * ~60 MB DXF with over two million pairs, and one small object each was enough
 * to push the converter renderer into an out-of-memory kill (measured on
 * `05_소방_기계/02_기계소방내진도면…dwg`, 89 533 entities).
 */
interface Pairs {
  lines: string[];
  codes: Int32Array;
  count: number;
}

/** Group code of pair `index`. */
function codeAt(pairs: Pairs, index: number): number {
  return index >= 0 && index < pairs.count ? (pairs.codes[index] ?? -1) : -1;
}

/** Value line of pair `index`, untrimmed. */
function valueAt(pairs: Pairs, index: number): string {
  return pairs.lines[index * 2 + 1] ?? '';
}

/** Index in `lines` of pair `index`'s group-code line. */
function lineAt(index: number): number {
  return index * 2;
}

/**
 * Reads the group code of every pair. Returns `null` when the text is not a
 * group-code stream (binary DXF, truncated file): the caller keeps it as is.
 */
function readPairs(lines: string[]): Pairs | null {
  const count = Math.floor(lines.length / 2);
  const codes = new Int32Array(count);
  for (let index = 0; index < count; index += 1) {
    const raw = lines[index * 2];
    if (raw === undefined || lines[index * 2 + 1] === undefined) {
      return { lines, codes: codes.subarray(0, index), count: index };
    }
    const code = Number.parseInt(raw, 10);
    if (Number.isNaN(code)) return null;
    codes[index] = code;
  }
  return { lines, codes, count };
}

/** Indentation-preserving group code line, e.g. `"  0"` → `" 66"`. */
function codeLine(sample: string, code: number): string {
  const text = String(code);
  const width = sample.length;
  const trimmed = sample.trimStart();
  const indent = width - trimmed.length;
  if (indent <= 0) return text;
  // dxfOut writes group codes right-aligned in a fixed field, like AutoCAD.
  const field = trimmed.length + indent;
  return text.padStart(Math.max(field, text.length), ' ');
}

interface EntityRecord {
  type: string;
  /** Index into `pairs` of the `0 <TYPE>` pair. */
  start: number;
  /** Index into `pairs` one past the last pair of this record. */
  end: number;
}

function readEntities(pairs: Pairs): EntityRecord[] {
  const records: EntityRecord[] = [];
  for (let index = 0; index < pairs.count; index += 1) {
    if (codeAt(pairs, index) !== 0) continue;
    const previous = records[records.length - 1];
    if (previous) previous.end = index;
    records.push({ type: valueAt(pairs, index).trim(), start: index, end: pairs.count });
  }
  return records;
}

/**
 * Where `66 1` goes inside an INSERT: right after the
 * `100 / AcDbBlockReference` subclass marker, which is where AutoCAD and ezdxf
 * write it (before group 2, the block name). Falls back to "just before group
 * 2" and finally to "just after the record's group 8" so a record with an
 * unusual layout still gets a valid flag.
 */
function insertionPointForAttributesFollow(pairs: Pairs, record: EntityRecord): number | null {
  let afterSubclass: number | null = null;
  let beforeBlockName: number | null = null;
  let afterLayer: number | null = null;
  for (let index = record.start + 1; index < record.end; index += 1) {
    const code = codeAt(pairs, index);
    if (code === 100 && valueAt(pairs, index).trim() === 'AcDbBlockReference') {
      afterSubclass = index + 1;
    }
    if (code === 2 && beforeBlockName === null) beforeBlockName = index;
    if (code === 8 && afterLayer === null) afterLayer = index + 1;
  }
  return afterSubclass ?? beforeBlockName ?? afterLayer;
}

/** DXF group 92 flags of one HATCH boundary path plus the points it spans. */
interface BoundaryPath {
  /** Index into `pairs` of the group-92 pair. */
  pairIndex: number;
  flags: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
  hasBox: boolean;
}

/**
 * Collects the boundary paths of one HATCH with a bounding box per path.
 *
 * The box comes from the 10/20 and 11/21 groups between this path's group 92
 * and the next one (or group 75, the hatch style, which always follows the
 * boundary block) — that covers polyline vertices as well as line/arc/ellipse
 * edge data. It is only ever used to decide *nesting*, never to compute an
 * area, so an approximate box for curved edges is good enough.
 */
function readBoundaryPaths(pairs: Pairs, record: EntityRecord): BoundaryPath[] {
  const paths: BoundaryPath[] = [];
  let current: BoundaryPath | null = null;
  let pendingX: number | null = null;
  const finish = (): void => {
    if (current) paths.push(current);
    current = null;
    pendingX = null;
  };
  for (let index = record.start + 1; index < record.end; index += 1) {
    const code = codeAt(pairs, index);
    if (code === 92) {
      finish();
      current = {
        pairIndex: index,
        flags: Number.parseInt(valueAt(pairs, index).trim(), 10) || 0,
        minX: Number.POSITIVE_INFINITY,
        minY: Number.POSITIVE_INFINITY,
        maxX: Number.NEGATIVE_INFINITY,
        maxY: Number.NEGATIVE_INFINITY,
        hasBox: false,
      };
      continue;
    }
    if (!current) continue;
    // Group 75 (hatch style) ends the boundary-path block; group 98 (seed
    // points) is even later. Both mean "no more boundary geometry".
    if (code === 75 || code === 98) {
      finish();
      continue;
    }
    if (code === 10 || code === 11) {
      const value = Number.parseFloat(valueAt(pairs, index));
      pendingX = Number.isFinite(value) ? value : null;
      continue;
    }
    if (code === 20 || code === 21) {
      const y = Number.parseFloat(valueAt(pairs, index));
      if (pendingX !== null && Number.isFinite(y)) {
        current.minX = Math.min(current.minX, pendingX);
        current.maxX = Math.max(current.maxX, pendingX);
        current.minY = Math.min(current.minY, y);
        current.maxY = Math.max(current.maxY, y);
        current.hasBox = true;
      }
      pendingX = null;
    }
  }
  finish();
  return paths;
}

/** True when `outer`'s box strictly contains `inner`'s. */
function contains(outer: BoundaryPath, inner: BoundaryPath): boolean {
  if (!outer.hasBox || !inner.hasBox) return false;
  return (
    outer.minX <= inner.minX &&
    outer.minY <= inner.minY &&
    outer.maxX >= inner.maxX &&
    outer.maxY >= inner.maxY &&
    (outer.minX < inner.minX ||
      outer.minY < inner.minY ||
      outer.maxX > inner.maxX ||
      outer.maxY > inner.maxY)
  );
}

/**
 * Restores the External bit on the outermost boundary paths of one HATCH.
 *
 * A path is outermost when an even number of other paths of the same hatch
 * contain it — depth 0 for a lone loop or several disjoint islands, depth 1 for
 * a hole (left alone), depth 2 for an island inside a hole (external again).
 * This is exactly the alternation `hatch_area()` in the engine assumes
 * (`external/outermost adds, everything else subtracts`), and it degrades to
 * "the first path is the external one" when the boxes carry no information,
 * which is the order AutoCAD and ezdxf write.
 */
function externalPathIndices(paths: BoundaryPath[]): number[] {
  const indices: number[] = [];
  const anyBox = paths.some((path) => path.hasBox);
  paths.forEach((path, index) => {
    if (!anyBox) {
      if (index === 0) indices.push(index);
      return;
    }
    let depth = 0;
    paths.forEach((other, otherIndex) => {
      if (otherIndex !== index && contains(other, path)) depth += 1;
    });
    if (depth % 2 === 0) indices.push(index);
  });
  return indices;
}

/** What the file declares about its own tables, read before anything is rewritten. */
interface DocumentTables {
  /** Every name in the DIMSTYLE table. */
  dimStyles: Set<string>;
  /** `$DIMSTYLE`, the drawing's active style. */
  activeDimStyle: string | null;
  /** `$HANDSEED` as a number, or 0 when absent/unparseable. */
  handSeed: number;
  /** Line index of the `$HANDSEED` value, so it can be bumped. */
  handSeedLine: number | null;
}

function readTables(pairs: Pairs, records: EntityRecord[]): DocumentTables {
  const dimStyles = new Set<string>();
  let activeDimStyle: string | null = null;
  let handSeed = 0;
  let handSeedLine: number | null = null;

  for (let index = 0; index < pairs.count; index += 1) {
    if (codeAt(pairs, index) !== 9) continue;
    const name = valueAt(pairs, index).trim();
    if (index + 1 >= pairs.count) continue;
    if (name === '$DIMSTYLE') activeDimStyle = valueAt(pairs, index + 1).trim();
    if (name === '$HANDSEED') {
      handSeed = Number.parseInt(valueAt(pairs, index + 1).trim(), 16);
      if (Number.isNaN(handSeed)) handSeed = 0;
      handSeedLine = lineAt(index + 1) + 1;
    }
  }

  for (const record of records) {
    if (record.type !== 'DIMSTYLE') continue;
    for (let index = record.start + 1; index < record.end; index += 1) {
      if (codeAt(pairs, index) === 2) {
        dimStyles.add(valueAt(pairs, index).trim());
        break;
      }
    }
  }
  return { dimStyles, activeDimStyle, handSeed, handSeedLine };
}

/**
 * The style a LEADER/DIMENSION should point at when its own name is unusable:
 * the drawing's active style, else `Standard`, else any defined style.
 */
function fallbackDimStyle(tables: DocumentTables): string | null {
  if (tables.activeDimStyle !== null && tables.dimStyles.has(tables.activeDimStyle)) {
    return tables.activeDimStyle;
  }
  if (tables.dimStyles.has('Standard')) return 'Standard';
  const [first] = [...tables.dimStyles].sort();
  return first ?? null;
}

/** Index of the first pair with `code` inside a record, or null. */
function findCode(pairs: Pairs, record: EntityRecord, code: number): number | null {
  for (let index = record.start + 1; index < record.end; index += 1) {
    if (codeAt(pairs, index) === code) return index;
  }
  return null;
}

/**
 * Applies the two ADR-0002 §3 repairs to a `dxfOut()` result.
 *
 * Idempotent: a DXF that already carries `66 1` and External bits comes back
 * byte-identical with `unchanged: true`.
 */
export function postProcessDxfOut(text: string): DxfPostProcessResult {
  const lineEnding: '\r\n' | '\n' = text.includes('\r\n') ? '\r\n' : '\n';
  const lines = text.split(/\r?\n/);
  const pairs = readPairs(lines);
  const report: DxfPostProcessReport = {
    insertsFlagged: 0,
    insertsAlreadyFlagged: 0,
    hatchLoopsFlagged: 0,
    hatchCount: 0,
    dimStylesRestored: 0,
    bigFontsCleared: 0,
    handlesReassigned: 0,
    lineEnding,
  };
  if (pairs === null || pairs.count === 0) {
    return { ...report, text, unchanged: true };
  }

  const records = readEntities(pairs);
  const tables = readTables(pairs, records);
  const dimStyleFallback = fallbackDimStyle(tables);
  /** Line index → group-code/value lines to insert before it. */
  const insertions = new Map<number, string[]>();
  /** Line index → replacement value line. */
  const replacements = new Map<number, string>();
  /** Handles already issued, so a repeat can be spotted and re-numbered. */
  const seenHandles = new Set<string>();
  let nextHandle = tables.handSeed;

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (!record) continue;

    // --- handle uniqueness -------------------------------------------------
    // DIMSTYLE is the one table whose entries carry their handle in group 105.
    const handleAt = HANDLE_REPAIR_BISECT ? findCode(pairs, record, record.type === 'DIMSTYLE' ? 105 : 5) : null;
    if (handleAt !== null) {
      const raw = valueAt(pairs, handleAt);
      const handle = raw.trim().toUpperCase();
      const numeric = Number.parseInt(handle, 16);
      if (seenHandles.has(handle)) {
        nextHandle += 1;
        const replacement = nextHandle.toString(16).toUpperCase();
        replacements.set(lineAt(handleAt) + 1, raw.replace(/\S+/, replacement));
        seenHandles.add(replacement);
        report.handlesReassigned += 1;
      } else {
        seenHandles.add(handle);
        if (!Number.isNaN(numeric) && numeric > nextHandle) nextHandle = numeric;
      }
    }

    // --- dimension style ---------------------------------------------------
    if (record.type === 'LEADER' || record.type === 'DIMENSION') {
      const at = findCode(pairs, record, DIMSTYLE_NAME_CODE);
      if (at !== null && dimStyleFallback !== null) {
        const raw = valueAt(pairs, at);
        if (!tables.dimStyles.has(raw.trim())) {
          replacements.set(lineAt(at) + 1, raw.replace(/\S.*$/, dimStyleFallback));
          report.dimStylesRestored += 1;
        }
      }
    }

    // --- big font ----------------------------------------------------------
    if (record.type === 'STYLE') {
      const at = findCode(pairs, record, BIGFONT_CODE);
      if (at !== null && valueAt(pairs, at).trim() === UNKNOWN_NAME) {
        replacements.set(lineAt(at) + 1, '');
        report.bigFontsCleared += 1;
      }
    }

    if (record.type === 'INSERT') {
      const next = records[index + 1];
      if (next?.type !== 'ATTRIB') continue;
      const existing = findCode(pairs, record, 66);
      if (existing !== null) {
        const raw = valueAt(pairs, existing);
        if (raw.trim() === '1') report.insertsAlreadyFlagged += 1;
        else replacements.set(lineAt(existing) + 1, raw.replace(/\S+/, '1'));
        continue;
      }
      const at = insertionPointForAttributesFollow(pairs, record);
      if (at === null || at >= pairs.count) continue;
      const sample = lines[lineAt(at)] ?? '  0';
      insertions.set(lineAt(at), [codeLine(sample, 66), '1']);
      report.insertsFlagged += 1;
      continue;
    }

    if (record.type === 'HATCH') {
      report.hatchCount += 1;
      const paths = readBoundaryPaths(pairs, record);
      if (paths.length === 0) continue;
      for (const pathIndex of externalPathIndices(paths)) {
        const path = paths[pathIndex];
        if (!path) continue;
        if ((path.flags & (EXTERNAL_BIT | OUTERMOST_BIT)) !== 0) continue;
        const valueLine = lineAt(path.pairIndex) + 1;
        const raw = lines[valueLine] ?? '';
        replacements.set(valueLine, raw.replace(/\d+/, String(path.flags | EXTERNAL_BIT)));
        report.hatchLoopsFlagged += 1;
      }
    }
  }

  if (report.handlesReassigned > 0 && tables.handSeedLine !== null) {
    const raw = lines[tables.handSeedLine] ?? '';
    replacements.set(
      tables.handSeedLine,
      raw.replace(/\S+/, (nextHandle + 1).toString(16).toUpperCase())
    );
  }

  if (insertions.size === 0 && replacements.size === 0) {
    return { ...report, text, unchanged: true };
  }

  const out: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const before = insertions.get(index);
    if (before) out.push(...before);
    out.push(replacements.get(index) ?? lines[index] ?? '');
  }
  return { ...report, text: out.join(lineEnding), unchanged: false };
}
