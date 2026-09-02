import { createHash } from "node:crypto";

/**
 * `text_hash` per docs/contracts/stats-definition.md: NFC-normalise each
 * text member (TEXT: the string; MTEXT: raw `contents` including control
 * codes; ATTRIB: its value), sort the set by ascending code point, join with
 * `\n`, sha1, first 16 hex chars. Empty set -> sha1("").slice(0, 16).
 *
 * Sorting uses code points (not UTF-16 code units) so a string is compared
 * the way `Array.from(str)` / `for...of` iterate it, which is
 * surrogate-pair-safe -- plain `<` on JS strings compares UTF-16 code units
 * and can disagree with code-point order across the BMP boundary.
 */

export function normalizeText(raw: string): string {
  return raw.normalize("NFC");
}

function compareByCodePoint(a: string, b: string): number {
  const ai = a[Symbol.iterator]();
  const bi = b[Symbol.iterator]();
  for (;;) {
    const an = ai.next();
    const bn = bi.next();
    if (an.done && bn.done) return 0;
    if (an.done) return -1;
    if (bn.done) return 1;
    const ac = an.value.codePointAt(0) ?? 0;
    const bc = bn.value.codePointAt(0) ?? 0;
    if (ac !== bc) return ac - bc;
  }
}

function sha1Hex16(text: string): string {
  return createHash("sha1").update(text, "utf8").digest("hex").slice(0, 16);
}

/** `texts` should already be NFC-normalised (see `normalizeText`). */
export function aggregateTextHash(texts: readonly string[]): string {
  const sorted = [...texts].sort(compareByCodePoint);
  return sha1Hex16(sorted.join("\n"));
}
