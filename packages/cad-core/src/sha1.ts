/**
 * Synchronous SHA-1 over UTF-8, used for the `text_hash` of
 * `docs/contracts/stats-definition.md`.
 *
 * `statsByLayer` is synchronous and has to produce the same digest in Node
 * (vitest, the desktop utility process) and in the browser. `node:crypto` is
 * unavailable in the renderer and `crypto.subtle.digest` is asynchronous, so
 * the 60 lines below are the only way to keep one synchronous code path.
 * `test/sha1.test.ts` pins the output against `node:crypto`.
 *
 * SHA-1 is used as a content fingerprint for cross-parser comparison only,
 * never for authentication.
 */

function utf8Bytes(text: string): Uint8Array {
  return new TextEncoder().encode(text);
}

function rotateLeft(value: number, bits: number): number {
  return ((value << bits) | (value >>> (32 - bits))) >>> 0;
}

/** Lowercase hex SHA-1 of the UTF-8 encoding of `text`. */
export function sha1Hex(text: string): string {
  const message = utf8Bytes(text);
  const bitLength = message.length * 8;
  // message + 0x80 + zero padding to 56 mod 64 + 8 length bytes
  const paddedLength = (((message.length + 8) >> 6) + 1) << 6;
  const buffer = new Uint8Array(paddedLength);
  buffer.set(message);
  buffer[message.length] = 0x80;
  const view = new DataView(buffer.buffer);
  // Bit lengths above 2^32 cannot occur for the strings hashed here, but the
  // high word is written anyway so the padding is spec-correct.
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x1_0000_0000), false);
  view.setUint32(paddedLength - 4, bitLength >>> 0, false);

  let h0 = 0x67452301;
  let h1 = 0xefcdab89;
  let h2 = 0x98badcfe;
  let h3 = 0x10325476;
  let h4 = 0xc3d2e1f0;
  const words = new Uint32Array(80);

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let index = 0; index < 16; index += 1) {
      words[index] = view.getUint32(offset + index * 4, false);
    }
    for (let index = 16; index < 80; index += 1) {
      words[index] = rotateLeft(
        (words[index - 3] ?? 0) ^ (words[index - 8] ?? 0) ^ (words[index - 14] ?? 0) ^ (words[index - 16] ?? 0),
        1
      );
    }
    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    for (let index = 0; index < 80; index += 1) {
      let f: number;
      let k: number;
      if (index < 20) {
        f = (b & c) | (~b & d);
        k = 0x5a827999;
      } else if (index < 40) {
        f = b ^ c ^ d;
        k = 0x6ed9eba1;
      } else if (index < 60) {
        f = (b & c) | (b & d) | (c & d);
        k = 0x8f1bbcdc;
      } else {
        f = b ^ c ^ d;
        k = 0xca62c1d6;
      }
      const temp = (rotateLeft(a, 5) + f + e + k + (words[index] ?? 0)) >>> 0;
      e = d;
      d = c;
      c = rotateLeft(b, 30);
      b = a;
      a = temp;
    }
    h0 = (h0 + a) >>> 0;
    h1 = (h1 + b) >>> 0;
    h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0;
    h4 = (h4 + e) >>> 0;
  }

  return [h0, h1, h2, h3, h4].map((word) => word.toString(16).padStart(8, '0')).join('');
}

/**
 * Sorts UTF-16 code units the way Python's `sorted()` sorts code points, which
 * is what `stats.py` on the engine side will do. JavaScript's default `<`
 * compares code units, so a supplementary character (a surrogate pair starting
 * at 0xD800) would sort *before* U+E000..U+FFFF instead of after. Lifting the
 * surrogate range above 0xFFFF restores code-point order without allocating.
 */
export function compareByCodePoint(left: string, right: string): number {
  const shared = Math.min(left.length, right.length);
  for (let index = 0; index < shared; index += 1) {
    const a = liftSurrogate(left.charCodeAt(index));
    const b = liftSurrogate(right.charCodeAt(index));
    if (a !== b) return a < b ? -1 : 1;
  }
  return left.length - right.length;
}

function liftSurrogate(unit: number): number {
  return unit >= 0xd800 && unit <= 0xdfff ? unit + 0x2800 : unit;
}

/**
 * `text_hash` of the stats contract: NFC-normalise every member, sort ascending
 * by code point, join with `\n`, sha1, keep the first 16 hex characters. An
 * empty set hashes the empty string, so it is still a valid `text_hash`.
 */
export function textHash(values: readonly string[]): string {
  const normalised = values.map((value) => value.normalize('NFC'));
  normalised.sort(compareByCodePoint);
  return sha1Hex(normalised.join('\n')).slice(0, 16);
}
