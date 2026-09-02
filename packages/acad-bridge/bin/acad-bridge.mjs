#!/usr/bin/env node

// src/commands/dwg2dxf.ts
import { parseArgs } from "util";

// src/acad/read.ts
import { readFileSync } from "fs";
import {
  DwgReader,
  DwgReaderConfiguration,
  DxfReader,
  DxfReaderConfiguration,
  NotificationType
} from "@node-projects/acad-ts";
function notificationDrop(e) {
  const label = NotificationType[e.notificationType];
  const exceptionSuffix = e.exception ? `: ${e.exception.message}` : "";
  return { reason: "read-notification", message: `[${label}] ${e.message}${exceptionSuffix}` };
}
function readDwgFile(path) {
  const buffer = readFileSync(path);
  const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  const drops = [];
  const configuration = new DwgReaderConfiguration();
  configuration.keepUnknownEntities = true;
  const doc = DwgReader.readFromStreamWithConfig(arrayBuffer, configuration, (_sender, e) => {
    if (e.notificationType !== NotificationType.None) drops.push(notificationDrop(e));
  });
  return { doc, drops };
}
function readDxfFile(path) {
  const buffer = readFileSync(path);
  const bytes = new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength);
  const drops = [];
  const configuration = new DxfReaderConfiguration();
  configuration.keepUnknownEntities = true;
  const doc = DxfReader.readFromStreamWithConfig(bytes, configuration, (_sender, e) => {
    if (e.notificationType !== NotificationType.None) drops.push(notificationDrop(e));
  });
  return { doc, drops };
}
function detectFormat(path) {
  const lower = path.toLowerCase();
  if (lower.endsWith(".dwg")) return "dwg";
  if (lower.endsWith(".dxf")) return "dxf";
  throw new Error(`Cannot tell DWG from DXF by extension: ${path} (rename with .dwg or .dxf)`);
}
function readCadFile(path) {
  return detectFormat(path) === "dwg" ? readDwgFile(path) : readDxfFile(path);
}

// src/acad/scan-unsupported.ts
import { Insert as Insert2, ProxyEntity, UnknownEntity } from "@node-projects/acad-ts";

// src/acad/walk.ts
import { Insert } from "@node-projects/acad-ts";
function* walkSpaceEntities(doc) {
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
function* expand(entity, space) {
  if (entity.objectName === "SEQEND" || entity.objectName === "VERTEX") return;
  yield { entity, space };
  if (entity instanceof Insert) {
    for (const attribute of entity.attributes) {
      if (attribute.objectName === "SEQEND" || attribute.objectName === "VERTEX") continue;
      yield { entity: attribute, space };
    }
  }
}

// src/acad/scan-unsupported.ts
function hex(handle) {
  return handle.toString(16).toUpperCase();
}
function scanUnsupported(doc) {
  const drops = [];
  for (const { entity, space } of walkSpaceEntities(doc)) {
    const layer = entity.layer.name;
    if (entity instanceof UnknownEntity) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "acad-ts could not resolve this entity to a known class (read as UnknownEntity)",
        entityType: entity.objectName || void 0,
        handle: hex(entity.handle),
        space,
        layer
      });
    } else if (entity instanceof ProxyEntity) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "entity persisted only as proxy graphics (ACAD_PROXY_ENTITY)",
        entityType: entity.dxfClass?.dxfName ?? "ACAD_PROXY_ENTITY",
        handle: hex(entity.handle),
        space,
        layer
      });
    } else if (entity instanceof Insert2 && !entity.block) {
      drops.push({
        reason: "acad-ts-unsupported",
        message: "INSERT references an unresolved block record",
        handle: hex(entity.handle),
        space,
        layer
      });
    }
  }
  return drops;
}

// src/acad/version.ts
import { ACadVersion } from "@node-projects/acad-ts";
var SUPPORTED = {
  AC1009: ACadVersion.AC1009,
  AC1012: ACadVersion.AC1012,
  AC1014: ACadVersion.AC1014,
  AC1015: ACadVersion.AC1015,
  AC1018: ACadVersion.AC1018,
  AC1021: ACadVersion.AC1021,
  AC1024: ACadVersion.AC1024,
  AC1027: ACadVersion.AC1027,
  AC1032: ACadVersion.AC1032
};
var DEFAULT_DXF2DWG_VERSION = "AC1027";
var DEFAULT_DWG2DXF_VERSION = "AC1032";
function parseVersionName(name) {
  const key = name.trim().toUpperCase();
  const version = SUPPORTED[key];
  if (version === void 0) {
    throw new Error(
      `Unsupported ACadVersion "${name}". Supported: ${Object.keys(SUPPORTED).join(", ")}`
    );
  }
  return version;
}
function versionName(version) {
  const name = ACadVersion[version];
  return typeof name === "string" ? name : `Unknown(${String(version)})`;
}

// src/acad/write.ts
import { writeFileSync } from "fs";
import { DwgWriter, DxfWriter } from "@node-projects/acad-ts";
function writeDwgFile(doc, outPath) {
  const bytes = DwgWriter.writeToBuffer(doc);
  writeFileSync(outPath, bytes);
}
function writeDxfFile(doc, outPath, binary = false) {
  const chunks = [];
  const sink = {
    write(value) {
      chunks.push(value);
    }
  };
  DxfWriter.writeToStream(sink, doc, binary);
  writeFileSync(outPath, chunks.join(""), "utf8");
}

// src/drops.ts
function buildDropsReport(source, producerVersion, drops) {
  return {
    source,
    producer: "acad-ts",
    producer_version: producerVersion,
    drops
  };
}
function dropsSidecarPath(outPath) {
  const lastDot = outPath.lastIndexOf(".");
  const lastSlash = Math.max(outPath.lastIndexOf("/"), outPath.lastIndexOf("\\"));
  const base = lastDot > lastSlash ? outPath.slice(0, lastDot) : outPath;
  return `${base}.drops.json`;
}

// src/util.ts
import { createHash } from "crypto";
import { readFileSync as readFileSync2, writeFileSync as writeFileSync2 } from "fs";
var ACAD_TS_VERSION = "3.1.0";
function sha256File(path) {
  return createHash("sha256").update(readFileSync2(path)).digest("hex");
}
function writeJsonFile(path, data) {
  writeFileSync2(path, `${JSON.stringify(data, null, 2)}
`, "utf8");
}

// src/commands/dwg2dxf.ts
var USAGE = "Usage: acad-bridge dwg2dxf <in.dwg> <out.dxf> [--version AC1032]";
function runDwg2Dxf(argv) {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { version: { type: "string", default: DEFAULT_DWG2DXF_VERSION } }
  });
  const [input, output] = positionals;
  if (!input || !output) {
    process.stderr.write(`${USAGE}
`);
    return 1;
  }
  const version = parseVersionName(values.version);
  const { doc, drops: readDrops } = readDwgFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);
  doc.header.version = version;
  writeDxfFile(doc, output);
  const allDrops = [...readDrops, ...scanUnsupported(doc)];
  writeJsonFile(dropsSidecarPath(output), buildDropsReport(input, ACAD_TS_VERSION, allDrops));
  process.stdout.write(`wrote ${output} (${allDrops.length.toString()} drops)
`);
  return 0;
}

// src/commands/dxf2dwg.ts
import { parseArgs as parseArgs2 } from "util";
var USAGE2 = "Usage: acad-bridge dxf2dwg <in.dxf> <out.dwg> [--version AC1027]";
function runDxf2Dwg(argv) {
  const { values, positionals } = parseArgs2({
    args: argv,
    allowPositionals: true,
    options: { version: { type: "string", default: DEFAULT_DXF2DWG_VERSION } }
  });
  const [input, output] = positionals;
  if (!input || !output) {
    process.stderr.write(`${USAGE2}
`);
    return 1;
  }
  const version = parseVersionName(values.version);
  const { doc, drops: readDrops } = readDxfFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);
  doc.header.version = version;
  writeDwgFile(doc, output);
  const allDrops = [...readDrops, ...scanUnsupported(doc)];
  writeJsonFile(dropsSidecarPath(output), buildDropsReport(input, ACAD_TS_VERSION, allDrops));
  process.stdout.write(`wrote ${output} (${allDrops.length.toString()} drops)
`);
  return 0;
}

// src/acad/stats-builder.ts
import {
  Hatch,
  Insert as Insert3,
  MText,
  ProxyEntity as ProxyEntity2,
  TextEntity,
  UnknownEntity as UnknownEntity2,
  XYZ
} from "@node-projects/acad-ts";

// src/acad/entity-types.ts
var KEY_PATTERN = /^[A-Z][A-Z0-9_]*$/;
var SEMANTIC_RENAME = /* @__PURE__ */ new Map([["ARC_DIMENSION", "DIMENSION"]]);
function statsTypeKey(objectName) {
  const key = SEMANTIC_RENAME.get(objectName) ?? objectName;
  return KEY_PATTERN.test(key) ? key : null;
}
var LENGTH_TYPES = /* @__PURE__ */ new Set([
  "LINE",
  "LWPOLYLINE",
  "POLYLINE",
  "ARC",
  "CIRCLE",
  "ELLIPSE",
  "SPLINE"
]);

// src/acad/hatch-area.ts
import { BoundaryPathFlags } from "@node-projects/acad-ts";
var EXTERNAL_OR_OUTERMOST = BoundaryPathFlags.External | BoundaryPathFlags.Outermost;
function shoelaceArea(points) {
  const n = points.length;
  if (n < 3) return 0;
  let acc = 0;
  for (let i = 0; i < n; i++) {
    const p1 = points[i];
    const p2 = points[(i + 1) % n];
    if (!p1 || !p2) continue;
    acc += p1.x * p2.y - p2.x * p1.y;
  }
  return Math.abs(acc) / 2;
}
function hatchArea(hatch) {
  let total = 0;
  for (const path of hatch.paths) {
    const points = path.getPoints();
    const area = shoelaceArea(points);
    const isHole = (path.flags & EXTERNAL_OR_OUTERMOST) === 0;
    total += isHole ? -area : area;
  }
  return total;
}

// src/acad/length.ts
import {
  Arc,
  Circle,
  Ellipse,
  Line,
  LwPolyline,
  Polyline2D,
  Polyline3D,
  Spline,
  Vertex2D
} from "@node-projects/acad-ts";
function dist3(a, b) {
  return Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
}
function dist2(a, b) {
  return Math.hypot(b.x - a.x, b.y - a.y);
}
function bulgeSegmentLength(a, b, bulge) {
  const chord = dist2(a, b);
  if (bulge) {
    const angle = 4 * Math.atan(bulge);
    if (angle) {
      const radius = Math.abs(chord / (2 * Math.sin(angle / 2)));
      return radius * Math.abs(angle);
    }
  }
  return chord;
}
function polylineLength(vertices, closed) {
  const n = vertices.length;
  if (n < 2) return 0;
  const segCount = closed ? n : n - 1;
  let total = 0;
  for (let i = 0; i < segCount; i++) {
    const a = vertices[i];
    const b = vertices[(i + 1) % n];
    if (!a || !b) continue;
    total += bulgeSegmentLength(a, b, a.bulge);
  }
  return total;
}
function flattenLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    if (!prev || !cur) continue;
    total += dist3(prev, cur);
  }
  return total;
}
function flatteningPrecision(controlPointCount) {
  return Math.min(2e3, Math.max(200, controlPointCount * 50));
}
function entityLength(entity) {
  if (entity instanceof Arc) {
    let span = (entity.endAngle - entity.startAngle) % (Math.PI * 2);
    if (span < 0) span += Math.PI * 2;
    if (span === 0) span = Math.PI * 2;
    return entity.radius * span;
  }
  if (entity instanceof Circle) {
    return 2 * Math.PI * entity.radius;
  }
  if (entity instanceof Line) {
    return dist3(entity.startPoint, entity.endPoint);
  }
  if (entity instanceof LwPolyline) {
    const vertices = entity.vertices.map((v) => ({
      x: v.location.x,
      y: v.location.y,
      bulge: v.bulge
    }));
    return polylineLength(vertices, entity.isClosed);
  }
  if (entity instanceof Polyline2D) {
    const vertices = [];
    for (const v of entity.vertices) {
      if (v instanceof Vertex2D) vertices.push({ x: v.location.x, y: v.location.y, bulge: v.bulge });
    }
    return polylineLength(vertices, entity.isClosed);
  }
  if (entity instanceof Polyline3D) {
    return 0;
  }
  if (entity instanceof Ellipse) {
    return flattenLength(entity.polygonalVertexes(flatteningPrecision(4)));
  }
  if (entity instanceof Spline) {
    return flattenLength(entity.polygonalVertexes(flatteningPrecision(entity.controlPoints.length || 4)));
  }
  return 0;
}

// src/acad/text.ts
import { createHash as createHash2 } from "crypto";
function normalizeText(raw) {
  return raw.normalize("NFC");
}
function compareByCodePoint(a, b) {
  const ai = a[Symbol.iterator]();
  const bi = b[Symbol.iterator]();
  for (; ; ) {
    const an = ai.next();
    const bn = bi.next();
    if (an.done && bn.done) return 0;
    if (an.done) return -1;
    if (bn.done) return 1;
    const ac = an.value.codePointAt(0) ?? 0;
    const bc = bn.value.codePointAt(0) ?? 0;
    if (ac !== bc) return ac - bc;
  }
}
function sha1Hex16(text) {
  return createHash2("sha1").update(text, "utf8").digest("hex").slice(0, 16);
}
function aggregateTextHash(texts) {
  const sorted = [...texts].sort(compareByCodePoint);
  return sha1Hex16(sorted.join("\n"));
}

// src/acad/stats-builder.ts
function newAccumulator(layer, space) {
  return {
    layer,
    space,
    entityCount: 0,
    countByType: /* @__PURE__ */ new Map(),
    lengthSum: 0,
    hatchAreaSum: 0,
    texts: [],
    insertByBlock: /* @__PURE__ */ new Map(),
    bboxMin: null,
    bboxMax: null
  };
}
function bucketFor(buckets, space, layer) {
  const key = `${space}\0${layer}`;
  let bucket = buckets.get(key);
  if (!bucket) {
    bucket = newAccumulator(layer, space);
    buckets.set(key, bucket);
  }
  return bucket;
}
function hex2(handle) {
  return handle.toString(16).toUpperCase();
}
function unionBBox(acc, entity, space, drops) {
  let bb;
  try {
    bb = entity.getBoundingBox();
  } catch (err) {
    drops.push({
      reason: "acad-ts-unsupported",
      message: `entity.getBoundingBox() threw (${err instanceof Error ? err.message : String(err)}); excluded from bbox`,
      entityType: entity.objectName || void 0,
      handle: hex2(entity.handle),
      space,
      layer: entity.layer.name
    });
    return;
  }
  if (!bb) return;
  const { min, max } = bb;
  if (![min.x, min.y, min.z, max.x, max.y, max.z].every(Number.isFinite)) return;
  if (!acc.bboxMin || !acc.bboxMax) {
    acc.bboxMin = new XYZ(min.x, min.y, min.z);
    acc.bboxMax = new XYZ(max.x, max.y, max.z);
    return;
  }
  acc.bboxMin.x = Math.min(acc.bboxMin.x, min.x);
  acc.bboxMin.y = Math.min(acc.bboxMin.y, min.y);
  acc.bboxMin.z = Math.min(acc.bboxMin.z, min.z);
  acc.bboxMax.x = Math.max(acc.bboxMax.x, max.x);
  acc.bboxMax.y = Math.max(acc.bboxMax.y, max.y);
  acc.bboxMax.z = Math.max(acc.bboxMax.z, max.z);
}
function textValueOf(entity) {
  if (entity instanceof MText) return entity.value;
  if (entity instanceof TextEntity) return entity.value;
  return "";
}
function processEntity(entity, space, buckets, drops) {
  const isUnknown = entity instanceof UnknownEntity2;
  const isProxy = entity instanceof ProxyEntity2;
  const normalized = statsTypeKey(entity.objectName || "ACAD_PROXY_ENTITY");
  const layerName = entity.layer.name;
  if (normalized === null) {
    drops.push({
      reason: "stats-schema-unsupported-type",
      message: `entity type '${entity.objectName}' does not fit the LayerStatsDocument count_by_type key pattern; excluded from stats`,
      entityType: entity.objectName,
      handle: hex2(entity.handle),
      space,
      layer: layerName
    });
    return;
  }
  if (isUnknown || isProxy) {
    drops.push({
      reason: "acad-ts-unsupported",
      message: isUnknown ? `acad-ts could not fully resolve this entity to a known class (read as UnknownEntity); counted under '${normalized}'` : `entity persisted only as proxy graphics (ACAD_PROXY_ENTITY); counted under '${normalized}'`,
      entityType: entity.objectName || void 0,
      handle: hex2(entity.handle),
      space,
      layer: layerName
    });
  }
  const bucket = bucketFor(buckets, space, layerName);
  if (normalized === "ATTRIB") {
    bucket.texts.push(normalizeText(textValueOf(entity)));
    return;
  }
  bucket.entityCount += 1;
  bucket.countByType.set(normalized, (bucket.countByType.get(normalized) ?? 0) + 1);
  if (LENGTH_TYPES.has(normalized)) bucket.lengthSum += entityLength(entity);
  if (normalized === "HATCH" && entity instanceof Hatch) bucket.hatchAreaSum += hatchArea(entity);
  if (normalized === "TEXT" || normalized === "MTEXT") {
    bucket.texts.push(normalizeText(textValueOf(entity)));
  }
  if (normalized === "INSERT" && entity instanceof Insert3) {
    let blockName = entity.block?.name;
    if (blockName == null || blockName === "") {
      blockName = "<unresolved>";
      drops.push({
        reason: "acad-ts-unsupported",
        message: "INSERT references an unresolved block record",
        handle: hex2(entity.handle),
        space,
        layer: layerName
      });
    } else {
      blockName = blockName.normalize("NFC");
    }
    bucket.insertByBlock.set(blockName, (bucket.insertByBlock.get(blockName) ?? 0) + 1);
  }
  unionBBox(bucket, entity, space, drops);
}
function round6(n) {
  return Math.round(n * 1e6) / 1e6;
}
function finalizeAggregate(acc) {
  const countByType = {};
  for (const [type, count] of [...acc.countByType].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
    countByType[type] = count;
  }
  const insertByBlock = {};
  for (const [block, count] of [...acc.insertByBlock].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0)) {
    insertByBlock[block] = count;
  }
  const aggregate = {
    entity_count: acc.entityCount,
    count_by_type: countByType,
    length_sum_mm: round6(acc.lengthSum),
    hatch_area_sum_mm2: round6(acc.hatchAreaSum),
    text_count: acc.texts.length,
    text_hash: aggregateTextHash(acc.texts),
    insert_by_block: insertByBlock
  };
  if (acc.bboxMin && acc.bboxMax) {
    aggregate.bbox = {
      min: [acc.bboxMin.x, acc.bboxMin.y, acc.bboxMin.z],
      max: [acc.bboxMax.x, acc.bboxMax.y, acc.bboxMax.z]
    };
  }
  return aggregate;
}
function mergeAccumulators(accumulators) {
  const total = newAccumulator("", "");
  for (const acc of accumulators) {
    total.entityCount += acc.entityCount;
    for (const [type, count] of acc.countByType) total.countByType.set(type, (total.countByType.get(type) ?? 0) + count);
    total.lengthSum += acc.lengthSum;
    total.hatchAreaSum += acc.hatchAreaSum;
    total.texts.push(...acc.texts);
    for (const [block, count] of acc.insertByBlock) {
      total.insertByBlock.set(block, (total.insertByBlock.get(block) ?? 0) + count);
    }
    if (acc.bboxMin && acc.bboxMax) {
      if (!total.bboxMin || !total.bboxMax) {
        total.bboxMin = new XYZ(acc.bboxMin.x, acc.bboxMin.y, acc.bboxMin.z);
        total.bboxMax = new XYZ(acc.bboxMax.x, acc.bboxMax.y, acc.bboxMax.z);
      } else {
        total.bboxMin.x = Math.min(total.bboxMin.x, acc.bboxMin.x);
        total.bboxMin.y = Math.min(total.bboxMin.y, acc.bboxMin.y);
        total.bboxMin.z = Math.min(total.bboxMin.z, acc.bboxMin.z);
        total.bboxMax.x = Math.max(total.bboxMax.x, acc.bboxMax.x);
        total.bboxMax.y = Math.max(total.bboxMax.y, acc.bboxMax.y);
        total.bboxMax.z = Math.max(total.bboxMax.z, acc.bboxMax.z);
      }
    }
  }
  return total;
}
function compareBuckets(a, b) {
  if (a.layer !== b.layer) return a.layer < b.layer ? -1 : 1;
  if (a.space !== b.space) return a.space < b.space ? -1 : 1;
  return 0;
}
function buildStats(doc) {
  if (!doc.modelSpace) throw new Error("document has no model space");
  const buckets = /* @__PURE__ */ new Map();
  const drops = [];
  for (const { entity, space } of walkSpaceEntities(doc)) {
    processEntity(entity, space, buckets, drops);
  }
  const sortedBuckets = [...buckets.values()].sort(compareBuckets);
  return {
    buckets: sortedBuckets.map((acc) => ({ layer: acc.layer, space: acc.space, aggregate: finalizeAggregate(acc) })),
    totals: finalizeAggregate(mergeAccumulators(buckets.values())),
    drops
  };
}

// src/commands/info.ts
var USAGE3 = "Usage: acad-bridge info <in.dwg|in.dxf>";
function runInfo(argv) {
  const [input] = argv;
  if (!input) {
    process.stderr.write(`${USAGE3}
`);
    return 1;
  }
  const { doc } = readCadFile(input);
  if (!doc.header) throw new Error(`${input}: document has no header`);
  const { totals } = buildStats(doc);
  const spaces = /* @__PURE__ */ new Set();
  if (doc.modelSpace && doc.modelSpace.entities.count > 0) spaces.add("MODEL");
  if (doc.layouts) {
    for (const layout of doc.layouts) {
      if (layout.name === "Model") continue;
      if ((layout.associatedBlock?.entities.count ?? 0) > 0) spaces.add(`PAPER:${layout.name}`);
    }
  }
  const info = {
    file: input,
    version: versionName(doc.header.version),
    code_page: doc.header.codePage,
    entity_count: totals.entity_count,
    count_by_type: totals.count_by_type,
    spaces: [...spaces].sort()
  };
  process.stdout.write(`${JSON.stringify(info, null, 2)}
`);
  return 0;
}

// src/commands/stats.ts
import { parseArgs as parseArgs3 } from "util";
import { assertValid, SCHEMA_VERSION, validateLayerStats } from "@halo-cad/schema";
var USAGE4 = "Usage: acad-bridge stats <in.dwg|in.dxf> --out <json>";
function runStats(argv) {
  const { values, positionals } = parseArgs3({
    args: argv,
    allowPositionals: true,
    options: { out: { type: "string" } }
  });
  const [input] = positionals;
  if (!input || !values.out) {
    process.stderr.write(`${USAGE4}
`);
    return 1;
  }
  const outPath = values.out;
  const { doc, drops: readDrops } = readCadFile(input);
  const { buckets, totals, drops: statsDrops } = buildStats(doc);
  const document = {
    schema_version: SCHEMA_VERSION,
    file_sha256: sha256File(input),
    producer: { name: "acad-ts", version: ACAD_TS_VERSION },
    buckets,
    totals
  };
  assertValid(validateLayerStats, document, `stats(${input})`);
  writeJsonFile(outPath, document);
  const allDrops = [...readDrops, ...statsDrops];
  writeJsonFile(dropsSidecarPath(outPath), buildDropsReport(input, ACAD_TS_VERSION, allDrops));
  process.stdout.write(
    `wrote ${outPath} (${String(buckets.length)} buckets, ${String(totals.entity_count)} entities, ${String(allDrops.length)} drops)
`
  );
  return 0;
}

// src/cli.ts
var USAGE5 = `acad-bridge -- @node-projects/acad-ts DWG/DXF bridge (Halo CAD W2-05)

Usage:
  acad-bridge dwg2dxf <in.dwg> <out.dxf> [--version AC1032]
  acad-bridge dxf2dwg <in.dxf> <out.dwg> [--version AC1027]
  acad-bridge stats <in.dwg|in.dxf> --out <json>
  acad-bridge info <in.dwg|in.dxf>
`;
function main(argv) {
  const [command, ...rest] = argv;
  switch (command) {
    case "dwg2dxf":
      return runDwg2Dxf(rest);
    case "dxf2dwg":
      return runDxf2Dwg(rest);
    case "stats":
      return runStats(rest);
    case "info":
      return runInfo(rest);
    case "-h":
    case "--help":
      process.stdout.write(USAGE5);
      return 0;
    case void 0:
      process.stderr.write(USAGE5);
      return 1;
    default:
      process.stderr.write(`Unknown command: ${command}

${USAGE5}`);
      return 1;
  }
}
try {
  process.exitCode = main(process.argv.slice(2));
} catch (err) {
  const message = err instanceof Error ? err.stack ?? err.message : String(err);
  process.stderr.write(`${message}
`);
  process.exitCode = 1;
}
//# sourceMappingURL=acad-bridge.mjs.map