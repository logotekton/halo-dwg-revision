import type { ErrorObject, ValidateFunction } from "ajv";
import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";

import type { BridgeMessage } from "../gen/ts/bridge/messages";
import type { EntityRef } from "../gen/ts/common/entity-ref";
import type { Provenance } from "../gen/ts/common/provenance";
import type { ConsistencyCheckSet } from "../gen/ts/levels/consistency-check";
import type { FloorLevelsDocument } from "../gen/ts/levels/floor-levels";
import type { LevelObservation } from "../gen/ts/levels/level-observation";
import type { NdjDocument } from "../gen/ts/ndj/document";
import type { NdjEntity } from "../gen/ts/ndj/entity";
import type { MarkupSidecar } from "../gen/ts/sidecar/markup";
import type { TagsSidecar } from "../gen/ts/sidecar/tags";
import type { LayerStatsDocument } from "../gen/ts/stats/layer-stats";
import { ALL_SCHEMAS, CONSISTENCY_CHECK_POINTER, SCHEMA_IDS } from "./schemas";

/** One check definition out of a {@link ConsistencyCheckSet}. */
export type ConsistencyCheck = ConsistencyCheckSet["checks"][number];

/**
 * Builds an ajv instance with every Halo CAD schema registered.
 *
 * Two strict sub-checks are off by design. `strictTypes` would demand a `type`
 * repeated next to every keyword that narrows a property from an `allOf` branch
 * or an `if` / `then` pair, burying the intent in noise. `strictRequired` would
 * reject exactly the pattern the height rules are built on: a `then` that says
 * `required: ["sl_source_observation_id"]` about a property declared in the
 * sibling fields schema. Every other strict check stays on, so a typo in a
 * keyword name is still a hard error.
 */
export function createValidator(): Ajv2020 {
  const ajv = new Ajv2020({
    strict: true,
    strictTypes: false,
    strictRequired: false,
    allowUnionTypes: true,
    allErrors: true,
    // Documents are stored and diffed as written; nothing is filled in behind
    // the producer's back, so `default` is documentation only.
    useDefaults: false,
  });
  addFormats(ajv);
  // Annotation-only keywords: `x-discriminator` documents the `oneOf` branch
  // selector, `tsType` steers the TypeScript generator. Neither validates.
  ajv.addVocabulary(["x-discriminator", "tsType"]);
  for (const schema of ALL_SCHEMAS) ajv.addSchema(schema);
  return ajv;
}

/** Shared instance. Compiling the schema set costs a few milliseconds. */
export const ajv: Ajv2020 = createValidator();

function compiledFor<T>(uri: string): ValidateFunction<T> {
  const validate = ajv.getSchema<T>(uri);
  if (!validate) throw new Error(`schema not registered: ${uri}`);
  return validate;
}

export const validateProvenance = compiledFor<Provenance>(SCHEMA_IDS.provenance);
export const validateEntityRef = compiledFor<EntityRef>(SCHEMA_IDS.entityRef);
export const validateNdjDocument = compiledFor<NdjDocument>(SCHEMA_IDS.ndjDocument);
export const validateNdjEntity = compiledFor<NdjEntity>(SCHEMA_IDS.ndjEntity);
export const validateLayerStats = compiledFor<LayerStatsDocument>(SCHEMA_IDS.layerStats);
export const validateLevelObservation = compiledFor<LevelObservation>(SCHEMA_IDS.levelObservation);
export const validateFloorLevels = compiledFor<FloorLevelsDocument>(SCHEMA_IDS.floorLevels);
export const validateConsistencyCheckSet = compiledFor<ConsistencyCheckSet>(
  SCHEMA_IDS.consistencyCheckSet
);
export const validateConsistencyCheck = compiledFor<ConsistencyCheck>(CONSISTENCY_CHECK_POINTER);
export const validateMarkupSidecar = compiledFor<MarkupSidecar>(SCHEMA_IDS.markupSidecar);
export const validateTagsSidecar = compiledFor<TagsSidecar>(SCHEMA_IDS.tagsSidecar);
export const validateBridgeMessage = compiledFor<BridgeMessage>(SCHEMA_IDS.bridgeMessage);

/** A single reason a document was rejected, flattened for logs and for the UI. */
export interface ValidationFailure {
  /** JSON Pointer into the instance, `""` for the document root. */
  path: string;
  keyword: string;
  message: string;
  params: Record<string, unknown>;
}

export function formatErrors(errors: readonly ErrorObject[] | null | undefined): ValidationFailure[] {
  if (!errors) return [];
  return errors.map((error) => ({
    path: error.instancePath,
    keyword: error.keyword,
    message: error.message ?? "is invalid",
    params: error.params as Record<string, unknown>,
  }));
}

export class SchemaValidationError extends Error {
  readonly failures: ValidationFailure[];
  readonly schemaId: string | undefined;

  constructor(label: string, failures: ValidationFailure[], schemaId?: string) {
    const detail = failures
      .map((failure) => `${failure.path === "" ? "/" : failure.path}: ${failure.message}`)
      .join("; ");
    super(`${label} failed schema validation: ${detail}`);
    this.name = "SchemaValidationError";
    this.failures = failures;
    this.schemaId = schemaId;
  }
}

/**
 * Narrows `data` to `T` or throws with every failure listed. Use at every
 * boundary where a document arrives from the other language.
 */
export function assertValid<T>(
  validate: ValidateFunction<T>,
  data: unknown,
  label = "document"
): T {
  if (validate(data)) return data;
  const schemaId =
    typeof validate.schema === "object" && validate.schema !== null
      ? (validate.schema as { $id?: string }).$id
      : undefined;
  throw new SchemaValidationError(label, formatErrors(validate.errors), schemaId);
}

/** Validation failures of the last call to `validate`, already flattened. */
export function failuresOf(validate: ValidateFunction<unknown>): ValidationFailure[] {
  return formatErrors(validate.errors);
}
