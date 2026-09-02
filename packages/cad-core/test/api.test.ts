/**
 * The public surface listed in `docs/briefs/W2-02.md` Constraints, plus the
 * behaviours the rest of the workspace will rely on: the schema version stays
 * in step with `@halo-cad/schema`, `dispose` really releases, and `entityRef`
 * produces evidence the schema accepts.
 */

import { SCHEMA_VERSION as SCHEMA_PACKAGE_VERSION, assertValid, validateEntityRef } from '@halo-cad/schema';
import { describe, expect, it } from 'vitest';

import * as api from '../src/index';
import { dispose, entityRef, openDxf, statsByLayer } from '../src/index';
import { fixtureBytes, sha256Of } from './helpers';

describe('public API', () => {
  it('exports exactly the entry points the brief asks for', () => {
    for (const name of [
      'openDxf',
      'statsByLayer',
      'exportNdj',
      'curveLength',
      'entityRef',
      'dispose',
    ]) {
      expect(typeof (api as unknown as Record<string, unknown>)[name], name).toBe('function');
    }
  });

  it('pins SCHEMA_VERSION to the schema package', () => {
    expect(api.SCHEMA_VERSION).toBe(SCHEMA_PACKAGE_VERSION);
  });

  it('normalises DXF record names onto the closed NDJ enum', () => {
    expect(api.normaliseEntityType('LWPOLYLINE')).toBe('LWPOLYLINE');
    expect(api.normaliseEntityType('MULTILEADER')).toBe('MLEADER');
    expect(api.normaliseEntityType('VIEWPORT')).toBe('PROXY');
    expect(api.normaliseEntityType('ACAD_TABLE')).toBe('PROXY');
  });

  it('strips MTEXT control codes for the plain rendering', () => {
    expect(api.mtextToPlain('지하 1층 평면도\\P축척 1:100\\P{\\C1;검토자 홍길동}')).toBe(
      '지하 1층 평면도\n축척 1:100\n검토자 홍길동'
    );
  });
});

describe('entityRef', () => {
  it('produces evidence that validates against entity-ref.schema.json', async () => {
    const bytes = fixtureBytes('F09.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const model = document.spaces().find((space) => space.space === 'MODEL');
      const entity = [...(model?.entities() ?? [])][0];
      expect(entity).toBeDefined();
      const reference = entityRef(entity!, { role: 'centerline' });
      assertValid(validateEntityRef, reference, 'entity ref');
      expect(reference.file).toBe(sha256);
      expect(reference.space).toBe('MODEL');
      expect(reference.role).toBe('centerline');
    } finally {
      dispose(document);
    }
  });

  it('refuses to invent a file identifier', async () => {
    const bytes = fixtureBytes('F09.dxf');
    const document = await openDxf(bytes);
    try {
      const model = document.spaces().find((space) => space.space === 'MODEL');
      const entity = [...(model?.entities() ?? [])][0];
      expect(() => entityRef(entity!)).toThrow(/file identifier/);
      expect(entityRef(entity!, { file: '0'.repeat(64) }).file).toBe('0'.repeat(64));
    } finally {
      dispose(document);
    }
  });
});

describe('dispose', () => {
  it('is idempotent and makes later access fail loudly', async () => {
    const bytes = fixtureBytes('F01.dxf');
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    expect(document.disposed).toBe(false);
    dispose(document);
    dispose(document);
    expect(document.disposed).toBe(true);
    expect(() => statsByLayer(document, { file_sha256: sha256 })).toThrow(/disposed/);
  });
});
