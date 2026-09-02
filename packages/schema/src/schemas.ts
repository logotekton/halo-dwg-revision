import type { SchemaObject } from "ajv";

import bridgeMessagesSchema from "./bridge/messages.schema.json";
import entityRefSchema from "./common/entity-ref.schema.json";
import primitivesSchema from "./common/primitives.schema.json";
import provenanceSchema from "./common/provenance.schema.json";
import consistencyCheckSetSchema from "./levels/consistency-check.schema.json";
import floorLevelsSchema from "./levels/floor-levels.schema.json";
import levelObservationSchema from "./levels/level-observation.schema.json";
import ndjDocumentSchema from "./ndj/document.schema.json";
import ndjEntitySchema from "./ndj/entity.schema.json";
import markupSchema from "./sidecar/markup.schema.json";
import tagsSchema from "./sidecar/tags.schema.json";
import layerStatsSchema from "./stats/layer-stats.schema.json";

/**
 * Base URI of every schema `$id`. `.internal` is reserved for private use, so
 * the URI is stable and can never resolve to something on the public internet:
 * schemas are always read from this package.
 */
export const SCHEMA_BASE_URI = "https://schema.halo-cad.internal/v0/";

/**
 * Current contract version, written into the `schema_version` field of every
 * top-level document. Major is bumped for a breaking change, minor for an
 * additive one. See packages/schema/README.md.
 */
export const SCHEMA_VERSION = "0.1";

/** Version of the 3D iframe postMessage protocol (ADR-0004). */
export const BRIDGE_PROTOCOL_VERSION = "0.1";

export const SCHEMA_IDS = {
  primitives: `${SCHEMA_BASE_URI}common/primitives.schema.json`,
  provenance: `${SCHEMA_BASE_URI}common/provenance.schema.json`,
  entityRef: `${SCHEMA_BASE_URI}common/entity-ref.schema.json`,
  ndjDocument: `${SCHEMA_BASE_URI}ndj/document.schema.json`,
  ndjEntity: `${SCHEMA_BASE_URI}ndj/entity.schema.json`,
  layerStats: `${SCHEMA_BASE_URI}stats/layer-stats.schema.json`,
  levelObservation: `${SCHEMA_BASE_URI}levels/level-observation.schema.json`,
  floorLevels: `${SCHEMA_BASE_URI}levels/floor-levels.schema.json`,
  consistencyCheckSet: `${SCHEMA_BASE_URI}levels/consistency-check.schema.json`,
  markupSidecar: `${SCHEMA_BASE_URI}sidecar/markup.schema.json`,
  tagsSidecar: `${SCHEMA_BASE_URI}sidecar/tags.schema.json`,
  bridgeMessage: `${SCHEMA_BASE_URI}bridge/messages.schema.json`,
} as const;

export type SchemaKey = keyof typeof SCHEMA_IDS;

/**
 * Pointer to the single check definition inside the consistency check set.
 * Rule authors validate one definition at a time against this.
 */
export const CONSISTENCY_CHECK_POINTER = `${SCHEMA_IDS.consistencyCheckSet}#/$defs/check`;

/**
 * Every schema source, keyed the same way as {@link SCHEMA_IDS}. Load order does
 * not matter: ajv resolves the absolute `$ref`s once all of them are registered.
 */
export const SCHEMAS: Record<SchemaKey, SchemaObject> = {
  primitives: primitivesSchema as SchemaObject,
  provenance: provenanceSchema as SchemaObject,
  entityRef: entityRefSchema as SchemaObject,
  ndjDocument: ndjDocumentSchema as SchemaObject,
  ndjEntity: ndjEntitySchema as SchemaObject,
  layerStats: layerStatsSchema as SchemaObject,
  levelObservation: levelObservationSchema as SchemaObject,
  floorLevels: floorLevelsSchema as SchemaObject,
  consistencyCheckSet: consistencyCheckSetSchema as SchemaObject,
  markupSidecar: markupSchema as SchemaObject,
  tagsSidecar: tagsSchema as SchemaObject,
  bridgeMessage: bridgeMessagesSchema as SchemaObject,
};

export const ALL_SCHEMAS: readonly SchemaObject[] = Object.values(SCHEMAS);
