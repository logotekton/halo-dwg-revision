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
  /** Line ending detected in the input, reused verbatim for inserted lines. */
  lineEnding: '\r\n' | '\n';
}

export interface DxfPostProcessResult extends DxfPostProcessReport {
  text: string;
  /** True when nothing had to change (the input was already conformant). */
  unchanged: boolean;
}

/** Bit 0 of DXF group 92: this boundary path is an external boundary. */
const EXTERNAL_BIT = 1;
/** Bit 4 of DXF group 92: outermost boundary; ezdxf accepts either as "adds area". */
const OUTERMOST_BIT = 16;

interface Pair {
  /** Index of the group-code line in `lines`. */
  index: number;
  code: number;
  value: string;
}

/**
 * Splits the file into group code / value pairs, keeping the raw line array so
 * the output can be rebuilt with every untouched line byte-identical.
 */
function readPairs(lines: string[]): Pair[] {
  const pairs: Pair[] = [];
  for (let index = 0; index + 1 < lines.length; index += 2) {
    const raw = lines[index];
    const value = lines[index + 1];
    if (raw === undefined || value === undefined) break;
    const code = Number.parseInt(raw.trim(), 10);
    if (Number.isNaN(code)) {
      // Not a group-code stream any more (binary DXF, truncated file): stop
      // rather than guess. The caller keeps the original text.
      return [];
    }
    pairs.push({ index, code, value });
  }
  return pairs;
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

function readEntities(pairs: Pair[]): EntityRecord[] {
  const records: EntityRecord[] = [];
  for (let index = 0; index < pairs.length; index += 1) {
    const pair = pairs[index];
    if (pair?.code !== 0) continue;
    const previous = records[records.length - 1];
    if (previous) previous.end = index;
    records.push({ type: pair.value.trim(), start: index, end: pairs.length });
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
function insertionPointForAttributesFollow(pairs: Pair[], record: EntityRecord): number | null {
  let afterSubclass: number | null = null;
  let beforeBlockName: number | null = null;
  let afterLayer: number | null = null;
  for (let index = record.start + 1; index < record.end; index += 1) {
    const pair = pairs[index];
    if (!pair) break;
    if (pair.code === 100 && pair.value.trim() === 'AcDbBlockReference') afterSubclass = index + 1;
    if (pair.code === 2 && beforeBlockName === null) beforeBlockName = index;
    if (pair.code === 8 && afterLayer === null) afterLayer = index + 1;
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
function readBoundaryPaths(pairs: Pair[], record: EntityRecord): BoundaryPath[] {
  const paths: BoundaryPath[] = [];
  let current: BoundaryPath | null = null;
  let pendingX: number | null = null;
  const finish = (): void => {
    if (current) paths.push(current);
    current = null;
    pendingX = null;
  };
  for (let index = record.start + 1; index < record.end; index += 1) {
    const pair = pairs[index];
    if (!pair) break;
    if (pair.code === 92) {
      finish();
      current = {
        pairIndex: index,
        flags: Number.parseInt(pair.value.trim(), 10) || 0,
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
    if (pair.code === 75 || pair.code === 98) {
      finish();
      continue;
    }
    if (pair.code === 10 || pair.code === 11) {
      const value = Number.parseFloat(pair.value);
      pendingX = Number.isFinite(value) ? value : null;
      continue;
    }
    if (pair.code === 20 || pair.code === 21) {
      const y = Number.parseFloat(pair.value);
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
    lineEnding,
  };
  if (pairs.length === 0) {
    return { ...report, text, unchanged: true };
  }

  const records = readEntities(pairs);
  /** Line index → group-code/value lines to insert before it. */
  const insertions = new Map<number, string[]>();
  /** Line index → replacement text (group 92 values only). */
  const replacements = new Map<number, string>();

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    if (!record) continue;

    if (record.type === 'INSERT') {
      const next = records[index + 1];
      if (next?.type !== 'ATTRIB') continue;
      let existing: Pair | null = null;
      for (let cursor = record.start + 1; cursor < record.end; cursor += 1) {
        const pair = pairs[cursor];
        if (pair?.code === 66) {
          existing = pair;
          break;
        }
      }
      if (existing) {
        if (existing.value.trim() === '1') report.insertsAlreadyFlagged += 1;
        else replacements.set(existing.index + 1, existing.value.replace(/\S+/, '1'));
        continue;
      }
      const at = insertionPointForAttributesFollow(pairs, record);
      const target = at === null ? null : pairs[at];
      if (!target) continue;
      const sample = lines[target.index] ?? '  0';
      insertions.set(target.index, [codeLine(sample, 66), '1']);
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
        const pair = pairs[path.pairIndex];
        if (!pair) continue;
        const raw = lines[pair.index + 1] ?? '';
        replacements.set(pair.index + 1, raw.replace(/\d+/, String(path.flags | EXTERNAL_BIT)));
        report.hatchLoopsFlagged += 1;
      }
    }
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
