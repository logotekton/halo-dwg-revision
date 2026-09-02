/**
 * The in-package SHA-1 has to agree with `node:crypto` byte for byte: the
 * engine computes `text_hash` with Python's `hashlib.sha1`, and the browser
 * build cannot use either.
 */

import { createHash } from 'node:crypto';

import { describe, expect, it } from 'vitest';

import { compareByCodePoint, sha1Hex, textHash } from '../src/index';

const SAMPLES = [
  '',
  'a',
  'abc',
  'The quick brown fox jumps over the lazy dog',
  '대명건설 신축공사',
  '지하 1층 평면도\n축척 1:100',
  '면적: 23.4㎡ Ø100',
  'x'.repeat(55),
  'x'.repeat(56),
  'x'.repeat(64),
  'x'.repeat(119),
  'x'.repeat(1000),
  '🏗️ 현장',
];

describe('sha1Hex', () => {
  it.each(SAMPLES)('matches node:crypto for %j', (sample) => {
    expect(sha1Hex(sample)).toBe(createHash('sha1').update(sample, 'utf8').digest('hex'));
  });
});

describe('textHash', () => {
  it('hashes the empty set as sha1("")', () => {
    expect(textHash([])).toBe(createHash('sha1').update('', 'utf8').digest('hex').slice(0, 16));
  });

  it('is order independent and NFC normalising', () => {
    // U+AC00 vs the decomposed U+1100 U+1161 spelling of the same syllable.
    const composed = '가';
    const decomposed = '가';
    expect(textHash([composed, 'b'])).toBe(textHash(['b', decomposed]));
  });

  it('sorts by code point, not by UTF-16 code unit', () => {
    // U+FFFD is one code unit, U+10000 is a surrogate pair whose lead unit
    // (0xD800) compares lower. Code-point order puts U+FFFD first.
    expect(compareByCodePoint('�', '\u{10000}')).toBeLessThan(0);
    expect('�' < '\u{10000}').toBe(false);
    const hash = textHash(['\u{10000}', '�']);
    expect(hash).toBe(
      createHash('sha1').update(`�\n\u{10000}`, 'utf8').digest('hex').slice(0, 16)
    );
  });

  it('produces a value the schema accepts', () => {
    expect(textHash(['거실', '주방'])).toMatch(/^[0-9a-f]{16}$/);
  });
});
