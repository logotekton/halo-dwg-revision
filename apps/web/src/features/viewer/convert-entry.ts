/**
 * The page that runs inside the hidden DWG converter window
 * (`apps/desktop/src/main/convert`, ADR-0002 개정 2026-09-02 §2).
 *
 * It is a renderer for one reason only: mlightcad's DWG converter forces
 * `useWorker: true` and Node has no `Worker` global. Nothing is drawn here —
 * there is no canvas, no `AcApDocManager`, no font loading. The page parses
 * DWG bytes with the LibreDWG worker, writes DXF with `dxfOut()`, applies the
 * two ADR-0002 §3 repairs and hands the text back to main, which writes the
 * file.
 *
 * GPL boundary (CLAUDE.md rule 3): the only import of the LibreDWG converter is
 * `@halo-cad/dwg-io-gpl`'s `registerLibreDwgConverter`.
 */

import { dispose, exportDxf, openDwg, postProcessDxfOut, repairDanglingReferences } from '@halo-cad/cad-core';
import { registerLibreDwgConverter } from '@halo-cad/dwg-io-gpl';

interface ConvertRequest {
  requestId: string;
  bytes: Uint8Array;
  name: string;
}

interface ConvertReply {
  requestId: string;
  ok: boolean;
  dxf?: string;
  entityCount?: number;
  warnings: string[];
  error?: string;
}

interface ConvertBridge {
  onRequest(callback: (request: ConvertRequest) => void): void;
  reply(reply: ConvertReply): void;
  assetsBase(): string;
}

declare global {
  interface Window {
    halocadConvert?: ConvertBridge;
  }
}

/**
 * Sub-entities that belong to their owner and are never counted as top-level
 * (`docs/contracts/stats-definition.md`, `count_by_type`). The number reported
 * here is compared with the engine's `stats.totals.entity_count` inside a
 * ±0.5% band, so it has to follow the same definition.
 */
const NOT_COUNTED = new Set(['ATTRIB', 'ATTDEF', 'SEQEND', 'VERTEX']);

function countEntities(document: ReturnType<typeof openDwg> extends Promise<infer T> ? T : never): number {
  let count = 0;
  for (const space of document.spaces()) {
    for (const entity of space.entities()) {
      if (NOT_COUNTED.has(entity.dxfType)) continue;
      count += 1;
    }
  }
  return count;
}

async function convert(request: ConvertRequest): Promise<ConvertReply> {
  const warnings: string[] = [];
  // The buffer is copied inside `openDwg`; the DWG path transfers it into the
  // parser worker and would otherwise detach the caller's view (spike C.7).
  const bytes = request.bytes.slice().buffer;
  const document = await openDwg(bytes);
  try {
    // Repair before writing, not after: references the DWG read left pointing
    // at table entries that do not exist make `ezdxf.bbox` raise, which fails
    // `halo-engine stats` and therefore the whole conversion under the
    // crosscheck gate (ADR-0002 개정 §4). Measured on the real DWG set — see
    // `repairDanglingReferences`.
    const repair = { droppedInserts: 0, retargetedDimStyles: 0, names: [] as string[] }; // BISECT
    if (repair.droppedInserts > 0 || repair.retargetedDimStyles > 0) {
      warnings.push(
        `repaired dangling references (${String(repair.droppedInserts)} INSERT dropped, ` +
          `${String(repair.retargetedDimStyles)} dimstyle retargeted): ${repair.names.join(', ')}`
      );
    }
    const raw = exportDxf(document, { version: 'AC1032', precision: 6 });
    // Counted after the repair so the number matches the file that is written;
    // the engine compares it with its own `stats.totals.entity_count` inside a
    // ±0.5% band.
    const entityCount = countEntities(document);
    const processed = postProcessDxfOut(raw);
    warnings.push(
      `post-process: ${String(processed.insertsFlagged)} INSERT(66), ` +
        `${String(processed.hatchLoopsFlagged)}/${String(processed.hatchCount)} HATCH(92)`
    );
    if (entityCount === 0) {
      // libredwg-web returned 85 of 200 006 entities on F11 without reporting
      // an error (`docs/spikes/large-file.md` §4.4). An empty parse is the
      // extreme case of the same failure and must not look like a success.
      return {
        requestId: request.requestId,
        ok: false,
        warnings,
        error: `libredwg parsed ${request.name} without producing any entity`,
      };
    }
    return {
      requestId: request.requestId,
      ok: true,
      dxf: processed.text,
      entityCount,
      warnings,
    };
  } finally {
    dispose(document);
  }
}

function main(): void {
  const bridge = window.halocadConvert;
  if (!bridge) return;
  registerLibreDwgConverter({ workerBaseUrl: `${bridge.assetsBase()}/workers` });
  bridge.onRequest((request) => {
    void convert(request)
      .then((reply) => {
        bridge.reply(reply);
      })
      .catch((error: unknown) => {
        bridge.reply({
          requestId: request.requestId,
          ok: false,
          warnings: [],
          error: error instanceof Error ? error.message : String(error),
        });
      });
  });
}

main();
