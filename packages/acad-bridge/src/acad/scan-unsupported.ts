import { Insert, ProxyEntity, UnknownEntity, type CadDocument } from "@node-projects/acad-ts";

import type { DropEntry } from "../drops";

import { walkSpaceEntities } from "./walk";

function hex(handle: number): string {
  return handle.toString(16).toUpperCase();
}

/**
 * Lightweight pass used by `dwg2dxf`/`dxf2dwg`: flags entities acad-ts could
 * not fully resolve (`UnknownEntity`, `ProxyEntity`) or INSERTs with an
 * unresolved block reference, without building full stats aggregates. Stats
 * building (acad/stats-builder.ts) does its own equivalent check inline,
 * because it additionally needs to classify these as the schema's `PROXY`
 * type -- a concern conversions do not have.
 */
export function scanUnsupported(doc: CadDocument): DropEntry[] {
  const drops: DropEntry[] = [];
  for (const { entity, space } of walkSpaceEntities(doc)) {
    const layer = entity.layer.name;
    if (entity instanceof UnknownEntity) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "acad-ts could not resolve this entity to a known class (read as UnknownEntity)",
        entityType: entity.objectName || undefined,
        handle: hex(entity.handle),
        space,
        layer,
      });
    } else if (entity instanceof ProxyEntity) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "entity persisted only as proxy graphics (ACAD_PROXY_ENTITY)",
        entityType: entity.dxfClass?.dxfName ?? "ACAD_PROXY_ENTITY",
        handle: hex(entity.handle),
        space,
        layer,
      });
    } else if (entity instanceof Insert && !entity.block) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "INSERT references an unresolved block record",
        handle: hex(entity.handle),
        space,
        layer,
      });
    }
  }
  return drops;
}
