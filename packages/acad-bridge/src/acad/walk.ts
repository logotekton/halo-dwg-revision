import { Insert, type CadDocument, type Entity } from "@node-projects/acad-ts";

export interface SpaceEntity {
  entity: Entity;
  /** `MODEL` or `PAPER:<layout name>`, per common/primitives.schema.json#/$defs/space. */
  space: string;
}

/**
 * Walks every top-level entity of every non-empty space in `doc`: model
 * space, then each paper-space layout that actually has entities (layouts
 * named "Model", or with no entities, are skipped -- mirrors
 * fixtures_gen.stats.compute_stats on the ezdxf side). Entities inside block
 * *definitions* are never visited, only INSERTs of them (ADR-0002 6 /
 * stats-definition.md: "블록 정의 내부 엔티티는 세지 않는다").
 *
 * Each INSERT's ATTRIB children (`insert.attributes`, not part of
 * `blockRecord.entities`) are yielded right after their INSERT, in the same
 * space -- their own `layer` may differ from the INSERT's.
 */
export function* walkSpaceEntities(doc: CadDocument): Generator<SpaceEntity> {
  const modelSpace = doc.modelSpace;
  if (modelSpace) {
    for (const entity of modelSpace.entities) yield* expand(entity, "MODEL");
  }
  if (doc.layouts) {
    for (const layout of doc.layouts) {
      if (layout.name === "Model") continue;
      const blockRecord = layout.associatedBlock;
      if (!blockRecord || blockRecord.entities.count === 0) continue;
      const space = `PAPER:${layout.name}`;
      for (const entity of blockRecord.entities) yield* expand(entity, space);
    }
  }
}

function* expand(entity: Entity, space: string): Generator<SpaceEntity> {
  // SEQEND (Insert/Polyline vertex-collection terminator) and VERTEX (old-
  // style POLYLINE vertices) are only ever encountered here for malformed
  // documents -- normally they live inside their owner's own collection, not
  // `blockRecord.entities`. Skip them defensively rather than mis-count them.
  if (entity.objectName === "SEQEND" || entity.objectName === "VERTEX") return;
  yield { entity, space };
  if (entity instanceof Insert) {
    // `Insert.attributes` is typed `SeqendCollection<AttributeEntity>`, but
    // at runtime the array can hold the terminating SEQEND as a plain
    // element too (not only via the separate `.seqend` property) -- filter
    // by `objectName`, the same guard used for the top-level entity above,
    // rather than trusting the generic type parameter.
    for (const attribute of entity.attributes) {
      if (attribute.objectName === "SEQEND" || attribute.objectName === "VERTEX") continue;
      yield { entity: attribute, space };
    }
  }
}
