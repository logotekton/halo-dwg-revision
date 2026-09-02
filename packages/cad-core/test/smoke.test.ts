import { describe, expect, it } from 'vitest';

import { dispose, openDxf } from '../src/index';
import { fixtureBytes, sha256Of } from './helpers';

describe('openDxf', () => {
  it('reads a fixture headlessly through @mlightcad/data-model', async () => {
    const bytes = fixtureBytes('F01.dxf');
    const document = await openDxf(bytes, { fileSha256: sha256Of(bytes) });
    expect(document.header.dwgVersion).toBe('AC1032');
    expect(document.header.codepageDeclared).toBe('ANSI_1252');
    expect(document.header.codepageEffective).toBe('UTF-8');
    expect(document.header.insunits).toBe(4);
    const spaces = document.spaces();
    expect(spaces.map((space) => space.space)).toContain('MODEL');
    const model = spaces.find((space) => space.space === 'MODEL');
    expect([...(model?.entities() ?? [])]).toHaveLength(26);
    dispose(document);
    expect(document.disposed).toBe(true);
  });

  it('does not detach the caller buffer', async () => {
    const bytes = fixtureBytes('F01.dxf');
    const before = bytes.byteLength;
    const document = await openDxf(bytes);
    expect(bytes.byteLength).toBe(before);
    dispose(document);
  });
});
