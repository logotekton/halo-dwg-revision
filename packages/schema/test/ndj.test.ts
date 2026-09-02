import { describe, expect, it } from "vitest";

import { SCHEMAS } from "../src/schemas";
import { formatErrors, validateNdjDocument, validateNdjEntity } from "../src/validate";
import { clone, loadExample } from "./helpers";

type Entity = Record<string, unknown>;
type NdjDoc = { entities: Entity[]; header: Record<string, unknown> };

const ENTITY_TYPES = (
  SCHEMAS.ndjEntity as { $defs: { entity_type: { enum: string[] } } }
).$defs.entity_type.enum;

describe("NDJ entities", () => {
  it("rejects an entity whose provenance has no handle", () => {
    const bad = loadExample("entity.bad-missing-handle.json");
    expect(validateNdjEntity(bad)).toBe(false);
    const failures = formatErrors(validateNdjEntity.errors);
    expect(
      failures.some(
        (failure) =>
          failure.keyword === "required" &&
          (failure.params as { missingProperty?: string }).missingProperty === "handle"
      )
    ).toBe(true);
  });

  it("rejects an entity whose type is outside the closed v0 set", () => {
    const bad = loadExample("entity.bad-unknown-type.json");
    expect(validateNdjEntity(bad)).toBe(false);
  });

  it("rejects an entity with an unknown extra property", () => {
    const entity = clone(loadExample("entity.line.json")) as Entity;
    entity.thickness_mm = 12;
    expect(validateNdjEntity(entity)).toBe(false);
  });

  it("rejects a lower-case handle", () => {
    const entity = clone(loadExample("entity.line.json")) as Entity;
    (entity.provenance as Record<string, unknown>).handle = "2b0";
    expect(validateNdjEntity(entity)).toBe(false);
  });

  it("accepts a paper-space layout in `space` and rejects an unlabelled one", () => {
    const entity = clone(loadExample("entity.line.json")) as Entity;
    const provenance = entity.provenance as Record<string, unknown>;
    provenance.space = "PAPER:A1-S01";
    expect(validateNdjEntity(entity)).toBe(true);
    provenance.space = "PAPER:";
    expect(validateNdjEntity(entity)).toBe(false);
  });

  it("every entity of the F06 example validates on its own as well", () => {
    const doc = loadExample("f06.ndj.json") as NdjDoc;
    expect(validateNdjDocument(doc)).toBe(true);
    for (const entity of doc.entities) {
      if (!validateNdjEntity(entity)) {
        throw new Error(
          `entity ${JSON.stringify(entity.type)} failed: ${JSON.stringify(
            formatErrors(validateNdjEntity.errors)
          )}`
        );
      }
    }
  });

  it("carries the INSERT handle in the provenance path of its attribute", () => {
    const doc = loadExample("f06.ndj.json") as NdjDoc;
    const insert = doc.entities.find((entity) => entity.type === "INSERT")!;
    const attrib = doc.entities.find((entity) => entity.type === "ATTRIB")!;
    const insertHandle = (insert.provenance as { handle: string }).handle;
    expect((attrib.provenance as { path: string[] }).path).toEqual([insertHandle]);
  });

  it("requires provenance on every entity", () => {
    for (const entity of (loadExample("f06.ndj.json") as NdjDoc).entities) {
      const stripped = clone(entity);
      delete stripped.provenance;
      expect(validateNdjEntity(stripped)).toBe(false);
    }
  });

  it("rejects a document whose dwg_version predates AC1014", () => {
    const doc = clone(loadExample("f06.ndj.json")) as NdjDoc;
    doc.header.dwg_version = "AC1009";
    expect(validateNdjDocument(doc)).toBe(false);
  });

  it("declares exactly the twenty entity types of the brief", () => {
    expect(ENTITY_TYPES).toEqual([
      "LINE",
      "LWPOLYLINE",
      "POLYLINE",
      "ARC",
      "CIRCLE",
      "ELLIPSE",
      "SPLINE",
      "TEXT",
      "MTEXT",
      "ATTRIB",
      "ATTDEF",
      "INSERT",
      "HATCH",
      "DIMENSION",
      "LEADER",
      "MLEADER",
      "SOLID",
      "POINT",
      "3DFACE",
      "PROXY",
    ]);
  });
});
