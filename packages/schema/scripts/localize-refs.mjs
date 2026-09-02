#!/usr/bin/env node
// Writes a copy of `src/` into <out-dir> where every `$ref` is a file-relative
// path instead of an absolute `https://schema.halo-cad.internal/v0/...` URL,
// and the absolute `$id` is dropped.
//
// Only the Python generator needs this. `datamodel-code-generator` resolves
// `$ref` by URL and would try to download the schema origin, which is a
// reserved private-use domain that must never be fetched. ajv and the
// TypeScript generator read `src/` as it is committed.
//
// Usage: node scripts/localize-refs.mjs <out-dir>
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC_DIR = path.join(PKG_ROOT, "src");
const SCHEMA_ORIGIN = "https://schema.halo-cad.internal/v0/";

const outDir = process.argv[2];
if (!outDir) {
  process.stderr.write("usage: node scripts/localize-refs.mjs <out-dir>\n");
  process.exit(2);
}

async function collect(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) found.push(...(await collect(full)));
    else if (entry.name.endsWith(".schema.json")) found.push(path.relative(SRC_DIR, full));
  }
  return found.sort();
}

/** Rewrite one `$ref` value relative to the file it appears in. */
function localize(ref, selfRel) {
  if (!ref.startsWith(SCHEMA_ORIGIN)) return ref;
  const rest = ref.slice(SCHEMA_ORIGIN.length);
  const hash = rest.indexOf("#");
  const target = hash === -1 ? rest : rest.slice(0, hash);
  const pointer = hash === -1 ? "" : rest.slice(hash);
  // Same-file references keep the file name instead of collapsing to `#/...`.
  // A bare pointer is re-based onto whichever file happens to be pulling the
  // subschema in, which is how `common/primitives.schema.json#/$defs/bbox`
  // ended up looking for `ndj/ndj/entity.schema.json`.
  const from = path.posix.dirname(selfRel.split(path.sep).join("/"));
  // No `./` prefix: datamodel-code-generator resolves `./x.json` against the
  // referring file's directory a second time and looks for `ndj/ndj/x.json`.
  return `${path.posix.relative(from, target)}${pointer}`;
}

/**
 * Keywords dropped from the Python copy.
 *
 * `if` / `then` / `else` / `not` express the conditional rules (ADR-0003 height
 * comparisons, evidence requirements, markup point counts).
 * `datamodel-code-generator` cannot turn a conditional into a pydantic
 * constraint and silently ignores it, so the generated models describe the
 * shape only; the rules stay enforced by validating against the JSON Schema
 * itself, which `halo_schema.validation` does on the Python side too.
 * Carrying them into the generator only trips its `$ref` resolution.
 */
const DROPPED_KEYWORDS = new Set([
  "$id",
  "if",
  "then",
  "else",
  "not",
  "unevaluatedProperties",
  "tsType",
  "x-discriminator",
]);

function transform(node, selfRel) {
  if (Array.isArray(node)) return node.map((item) => transform(item, selfRel));
  if (node && typeof node === "object") {
    const out = {};
    for (const [key, value] of Object.entries(node)) {
      if (DROPPED_KEYWORDS.has(key)) continue;
      out[key] =
        key === "$ref" && typeof value === "string"
          ? localize(value, selfRel)
          : transform(value, selfRel);
    }
    return out;
  }
  return node;
}

const relPaths = await collect(SRC_DIR);
await rm(outDir, { recursive: true, force: true });
for (const rel of relPaths) {
  const schema = JSON.parse(await readFile(path.join(SRC_DIR, rel), "utf8"));
  const target = path.join(outDir, rel);
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, `${JSON.stringify(transform(schema, rel), null, 2)}\n`, "utf8");
}
process.stdout.write(`localized ${relPaths.length} schemas into ${outDir}\n`);
