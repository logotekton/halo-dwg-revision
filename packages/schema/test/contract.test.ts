import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import {
  ALL_SCHEMAS,
  BRIDGE_PROTOCOL_VERSION,
  SCHEMA_BASE_URI,
  SCHEMA_IDS,
  SCHEMA_VERSION,
  SCHEMAS,
} from "../src/schemas";
import {
  SchemaValidationError,
  assertValid,
  createValidator,
  validateBridgeMessage,
  validateEntityRef,
  validateLevelObservation,
  validateProvenance,
} from "../src/validate";
import { PACKAGE_ROOT, clone, loadExample } from "./helpers";

/** Schema sources, relative to `src/`, in the order they are listed. */
const SCHEMA_SOURCE_FILES = Object.entries(SCHEMA_IDS).map(([, id]) =>
  id.slice(SCHEMA_BASE_URI.length)
);

describe("schema registry", () => {
  it("registers every schema under its own $id", () => {
    for (const [key, id] of Object.entries(SCHEMA_IDS)) {
      const schema = SCHEMAS[key as keyof typeof SCHEMAS] as { $id?: string };
      expect(schema.$id).toBe(id);
    }
  });

  it("gives every schema a title, a description and the 2020-12 dialect", () => {
    for (const schema of ALL_SCHEMAS) {
      const s = schema as { $id?: string; $schema?: string; title?: string; description?: string };
      expect(s.$schema).toBe("https://json-schema.org/draft/2020-12/schema");
      expect(s.title, `${s.$id} has no title`).toBeTruthy();
      expect(s.description, `${s.$id} has no description`).toBeTruthy();
    }
  });

  it("uses only absolute in-package $refs, so no schema reaches the network", () => {
    const seen: string[] = [];
    const walk = (node: unknown): void => {
      if (Array.isArray(node)) {
        node.forEach(walk);
        return;
      }
      if (node && typeof node === "object") {
        for (const [key, value] of Object.entries(node)) {
          if (key === "$ref" && typeof value === "string") seen.push(value);
          else walk(value);
        }
      }
    };
    ALL_SCHEMAS.forEach(walk);
    expect(seen.length).toBeGreaterThan(100);
    for (const ref of seen) {
      expect(ref.startsWith(SCHEMA_BASE_URI), `unexpected $ref: ${ref}`).toBe(true);
    }
  });

  it("compiles a fresh validator without strict-mode complaints", () => {
    expect(() => createValidator()).not.toThrow();
  });

  it("pins the contract and bridge protocol versions", () => {
    expect(SCHEMA_VERSION).toBe("0.1");
    expect(BRIDGE_PROTOCOL_VERSION).toBe("0.1");
  });

  it("stamps every top-level document example with the current schema_version", () => {
    for (const name of ["f06.ndj.json", "layer-stats.f06.json", "levels.ok.json", "tags.json"]) {
      const doc = loadExample(name) as { schema_version: string };
      expect(doc.schema_version, name).toBe(SCHEMA_VERSION);
    }
  });
});

describe("provenance and evidence", () => {
  const provenance = {
    file: "5747a89c5a08e33837a535af35cb18a88c0d2dc9a8b5a99e1a0a9d30b8ba0fe1",
    handle: "2B0",
    path: [],
    space: "MODEL",
  };

  it("accepts a sha256 or a ULID as the file identifier", () => {
    expect(validateProvenance(provenance)).toBe(true);
    expect(
      validateProvenance({ ...provenance, file: "4QQZQWAKSC9JFM0DR3AN3VVKB6" })
    ).toBe(true);
  });

  it("rejects a file identifier that is neither", () => {
    expect(validateProvenance({ ...provenance, file: "F06.dxf" })).toBe(false);
  });

  it("requires the INSERT path, even when empty", () => {
    const withoutPath: Record<string, unknown> = { ...provenance };
    delete withoutPath.path;
    expect(validateProvenance(withoutPath)).toBe(false);
  });

  it("treats an entity reference as a provenance with a role", () => {
    expect(validateEntityRef({ ...provenance, role: "dimension_text" })).toBe(true);
  });
});

describe("bridge messages", () => {
  it("rejects a message from a different protocol version", () => {
    const message = clone(loadExample("bridge.load.json")) as Record<string, unknown>;
    message.protocol_version = "0.2";
    expect(validateBridgeMessage(message)).toBe(false);
  });

  it("rejects a load URL that points outside the bundle and the loopback sidecar", () => {
    const message = clone(loadExample("bridge.load.json")) as {
      payload: Record<string, unknown>;
    };
    message.payload.url = "https://cdn.example.com/model.glb";
    expect(validateBridgeMessage(message)).toBe(false);
  });

  it("accepts the loopback sidecar origin", () => {
    const message = clone(loadExample("bridge.load.json")) as {
      payload: Record<string, unknown>;
    };
    message.payload.url = "http://127.0.0.1:8765/api/v1/model/3F.glb";
    expect(validateBridgeMessage(message)).toBe(true);
  });
});

describe("assertValid", () => {
  it("returns the value when it validates", () => {
    const observation = loadExample("levels.ok.json") as { observations: unknown[] };
    expect(assertValid(validateLevelObservation, observation.observations[0])).toBe(
      observation.observations[0]
    );
  });

  it("throws a SchemaValidationError listing every failure", () => {
    try {
      assertValid(validateProvenance, { space: "MODEL" }, "provenance");
      throw new Error("expected assertValid to throw");
    } catch (error) {
      expect(error).toBeInstanceOf(SchemaValidationError);
      const failures = (error as SchemaValidationError).failures;
      expect(failures.length).toBeGreaterThanOrEqual(3);
      expect((error as SchemaValidationError).schemaId).toBe(SCHEMA_IDS.provenance);
    }
  });
});

describe("generated artefacts", () => {
  it("exports a root type for every schema from the generated barrel", () => {
    const barrel = readFileSync(path.join(PACKAGE_ROOT, "gen", "ts", "index.d.ts"), "utf8");
    for (const schema of ALL_SCHEMAS) {
      const title = (schema as { title: string }).title;
      expect(barrel, `gen/ts/index.d.ts does not export ${title}`).toContain(`{ ${title} }`);
    }
  });

  it("keeps the generated declarations marked as generated", () => {
    const barrel = readFileSync(path.join(PACKAGE_ROOT, "gen", "ts", "index.d.ts"), "utf8");
    expect(barrel).toContain("DO NOT EDIT BY HAND");
  });

  it("ships the Python package a byte-identical copy of every schema source", () => {
    // gen/python/halo_schema/schemas is package data so the engine can validate
    // against the same rules the viewer does. It must never drift from src/.
    for (const rel of SCHEMA_SOURCE_FILES) {
      const source = readFileSync(path.join(PACKAGE_ROOT, "src", rel), "utf8");
      const shipped = readFileSync(
        path.join(PACKAGE_ROOT, "gen", "python", "halo_schema", "schemas", rel),
        "utf8"
      );
      expect(shipped, `${rel} differs between src/ and the Python package`).toBe(source);
    }
  });
});
