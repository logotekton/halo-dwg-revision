/**
 * ATTRIB collection, and the upstream limitation that hides it on the
 * fixtures.
 *
 * `docs/contracts/stats-definition.md` counts ATTRIB into `text_count` /
 * `text_hash` and attributes it to the ATTRIB's own layer, collected through
 * `AcDbBlockReference.attributeIterator()`. That works — but only when the
 * ATTRIB's DXF owner handle (group 330) is the owning INSERT.
 *
 * `AcDbDxfDocumentReader.linkOrDeferAttribute` (data-model 1.14.3) resolves the
 * owning block reference from group 330 and silently drops the ATTRIB when that
 * handle names anything else. ezdxf writes the *space* block record there, the
 * spelling the DXF reference documents for entities in the ENTITIES section, so
 * every ATTRIB of an ezdxf-written drawing — including the working DXF of
 * ADR-0002 — disappears. The second test pins that behaviour so it fails the
 * day it is fixed upstream or worked around here.
 *
 * `fixtures/attrib-owner-insert.dxf` is the W1-04 spike fixture
 * (`spikes/mlightcad/fixtures/F-spike-r2018.dxf`, sha256
 * 1faa34b5…4d8557a2), a hand-written R2018 DXF whose ATTRIB `107` is owned by
 * INSERT `106`.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { dispose, exportNdj, openDxf, statsByLayer } from '../src/index';
import { readArrayBuffer, sha256Of } from './helpers';

const FIXTURE = join(import.meta.dirname, 'fixtures', 'attrib-owner-insert.dxf');

function bytesWithAttribOwnedBySpace(): ArrayBuffer {
  const text = readFileSync(FIXTURE, 'latin1');
  // ATTRIB 107: rewrite its owner from INSERT 106 to the model-space BTR 1E,
  // which is exactly what ezdxf writes.
  const patched = text.replace('ATTRIB\r\n5\r\n107\r\n330\r\n106\r\n', 'ATTRIB\r\n5\r\n107\r\n330\r\n1E\r\n');
  expect(patched).not.toBe(text);
  const buffer = Buffer.from(patched, 'latin1');
  return buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength) as ArrayBuffer;
}

describe('ATTRIB', () => {
  it('is collected from its INSERT and attributed to its own layer', async () => {
    const bytes = readArrayBuffer(FIXTURE);
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const model = document.spaces().find((space) => space.space === 'MODEL');
      const insert = [...(model?.entities() ?? [])].find((entity) => entity.type === 'INSERT');
      expect(insert?.blockName()).toBe('TITLEBLK');
      const attributes = insert?.attributes() ?? [];
      expect(attributes).toHaveLength(1);
      const attribute = attributes[0];
      expect(attribute?.type).toBe('ATTRIB');
      expect(attribute?.handle).toBe('107');
      expect(attribute?.layer).toBe('A-TEXT');
      expect(attribute?.textValue()).toBe('대명건설 신축공사');
      // provenance.path ends with the owning INSERT (brief, NDJ constraints).
      expect(attribute?.path).toEqual(['106']);

      const stats = statsByLayer(document, { file_sha256: sha256 });
      // The INSERT sits on layer 0, its ATTRIB on A-TEXT: the ATTRIB is
      // counted on its own layer, never on the INSERT's.
      const textLayer = stats.buckets.find((bucket) => bucket.layer === 'A-TEXT');
      expect(textLayer?.aggregate.text_count).toBe(3); // TEXT + MTEXT + ATTRIB
      expect(textLayer?.aggregate.count_by_type['ATTRIB']).toBeUndefined();
      const zeroLayer = stats.buckets.find((bucket) => bucket.layer === '0');
      expect(zeroLayer?.aggregate.count_by_type['INSERT']).toBe(1);
      expect(zeroLayer?.aggregate.text_count).toBe(0);

      const ndj = exportNdj(document, { file_sha256: sha256 });
      const attrib = ndj.entities.find((entity) => entity.type === 'ATTRIB');
      expect(attrib?.provenance.path).toEqual(['106']);
      const ndjInsert = ndj.entities.find((entity) => entity.type === 'INSERT');
      expect(ndjInsert?.attribs).toEqual([
        {
          tag: 'TITLE',
          text: '대명건설 신축공사',
          provenance: { file: sha256, handle: '107', path: ['106'], space: 'MODEL' },
        },
      ]);
    } finally {
      dispose(document);
    }
  });

  it('is dropped by data-model 1.14.3 when group 330 names the space, as ezdxf writes it', async () => {
    const bytes = bytesWithAttribOwnedBySpace();
    const sha256 = sha256Of(bytes);
    const document = await openDxf(bytes, { fileSha256: sha256 });
    try {
      const model = document.spaces().find((space) => space.space === 'MODEL');
      const entities = [...(model?.entities() ?? [])];
      const insert = entities.find((entity) => entity.type === 'INSERT');
      expect(insert?.attributes()).toHaveLength(0);
      // Not smuggled into the space iterator either: the ATTRIB is simply gone.
      expect(entities.some((entity) => entity.type === 'ATTRIB')).toBe(false);
      const stats = statsByLayer(document, { file_sha256: sha256 });
      expect(stats.totals.text_count).toBe(2);
    } finally {
      dispose(document);
    }
  });
});
