/**
 * The import boundary, checked as a test as well as by ESLint and by the grep
 * in the W2-02 acceptance commands: `src/mlightcad-surface.ts` is the only file
 * of this package that may name `@mlightcad/*`, and nothing GPL may be named
 * at all (CLAUDE.md rule 3).
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(import.meta.dirname, '..', 'src');
const SURFACE = 'mlightcad-surface.ts';

function sources(directory: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) out.push(...sources(path));
    else if (entry.name.endsWith('.ts')) out.push(path);
  }
  return out;
}

describe('mlightcad import boundary', () => {
  const files = sources(SRC);

  it('finds the surface file and more than one other source', () => {
    expect(files.some((file) => file.endsWith(SURFACE))).toBe(true);
    expect(files.length).toBeGreaterThan(3);
  });

  it.each(files.filter((file) => !file.endsWith(SURFACE)))(
    '%s does not mention @mlightcad',
    (file) => {
      expect(readFileSync(file, 'utf8')).not.toContain('@mlightcad');
    }
  );

  it.each(files)('%s does not import a GPL package', (file) => {
    expect(readFileSync(file, 'utf8')).not.toContain('@mlightcad/libredwg');
  });

  it('keeps the public API free of mlightcad type names', () => {
    const index = readFileSync(join(SRC, 'index.ts'), 'utf8');
    expect(index).not.toMatch(/\bAcDb[A-Z]/);
    expect(index).not.toMatch(/\bAcGe[A-Z]/);
    expect(index).not.toMatch(/\bAcAp[A-Z]/);
  });
});
