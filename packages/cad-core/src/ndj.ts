/**
 * NDJ export: the normalised document of `ndj/document.schema.json`.
 *
 * One `NdjEntity` per top-level entity of every space, plus one per ATTRIB
 * owned by a block reference. An entity kind the parser cannot map onto the
 * closed 20-value enum becomes `PROXY` carrying its `original_type`, which is
 * what the schema reserves that branch for.
 */

import type { NdjDocument } from '@halo-cad/schema/gen/ts/ndj/document';
import type { NdjEntity } from '@halo-cad/schema/gen/ts/ndj/entity';
import type { Provenance } from '@halo-cad/schema/gen/ts/common/provenance';

import { SCHEMA_VERSION, VIEWER_PRODUCER } from './constants';
import type {
  CadDocumentHandle,
  CadEntity,
  CadEntityDetail,
  CadPolylineVertex,
  Vec3,
} from './surface-types';

type Point = [number, number] | [number, number, number];

export interface NdjMeta {
  /** sha256 of the working-DXF bytes both parsers read. */
  file_sha256: string;
  /** sha256 of the immutable original this working DXF was derived from. */
  original_sha256?: string;
  /** ULID of the `drawing_file` row when the document lives in a project bundle. */
  file_id?: string;
  /** Factor applied to raw coordinates to obtain millimetres. Defaults to 1. */
  unit_scale_to_mm?: number;
  producer_version?: string;
}

const DWG_VERSIONS: ReadonlySet<string> = new Set([
  'AC1014',
  'AC1015',
  'AC1018',
  'AC1021',
  'AC1024',
  'AC1027',
  'AC1032',
]);

function point(value: Vec3): Point {
  return value.z === 0 ? [value.x, value.y] : [value.x, value.y, value.z];
}

function points(values: readonly Vec3[]): Point[] {
  return values.map(point);
}

function vertexPoints(vertices: readonly CadPolylineVertex[]): Point[] {
  return vertices.map((vertex) => [vertex.x, vertex.y] as Point);
}

function bulges(vertices: readonly CadPolylineVertex[]): number[] | undefined {
  return vertices.some((vertex) => vertex.bulge !== 0)
    ? vertices.map((vertex) => vertex.bulge)
    : undefined;
}

/** Drops `undefined` members so the emitted JSON keeps `additionalProperties: false` happy. */
function compact<T extends object>(value: T): T {
  for (const key of Object.keys(value)) {
    if ((value as Record<string, unknown>)[key] === undefined) {
      delete (value as Record<string, unknown>)[key];
    }
  }
  return value;
}

function provenanceOf(entity: CadEntity, file: string): Provenance {
  return {
    file,
    handle: entity.handle.toUpperCase(),
    path: entity.path.map((handle) => handle.toUpperCase()),
    space: entity.space,
  };
}

/**
 * Positive-height fallback. `height_mm` / `char_height_mm` / `radius_mm` are
 * `exclusiveMinimum: 0` in the schema, and a drawing can legally carry a zero
 * text height (the value then comes from the text style at render time).
 * Emitting the smallest representable positive height keeps the document
 * valid and visibly wrong rather than silently dropping the entity.
 */
const MIN_POSITIVE = 1e-9;

function positive(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : MIN_POSITIVE;
}

function bodyOf(detail: CadEntityDetail): Record<string, unknown> {
  switch (detail.kind) {
    case 'LINE':
      return { type: 'LINE', start: point(detail.start), end: point(detail.end) };
    case 'LWPOLYLINE':
      return {
        type: 'LWPOLYLINE',
        vertices: vertexPoints(detail.vertices),
        bulges: bulges(detail.vertices),
        closed: detail.closed,
        elevation_mm: detail.elevationMm,
      };
    case 'POLYLINE':
      return {
        type: 'POLYLINE',
        polyline_kind: detail.polylineKind,
        vertices: vertexPoints(detail.vertices),
        bulges: bulges(detail.vertices),
        closed: detail.closed,
      };
    case 'ARC':
      return {
        type: 'ARC',
        center: point(detail.center),
        radius_mm: positive(detail.radiusMm),
        start_angle_deg: detail.startAngleDeg,
        end_angle_deg: detail.endAngleDeg,
        normal: point(detail.normal),
      };
    case 'CIRCLE':
      return {
        type: 'CIRCLE',
        center: point(detail.center),
        radius_mm: positive(detail.radiusMm),
        normal: point(detail.normal),
      };
    case 'ELLIPSE':
      return {
        type: 'ELLIPSE',
        center: point(detail.center),
        major_axis: point(detail.majorAxis),
        ratio: detail.ratio > 0 ? detail.ratio : MIN_POSITIVE,
        start_param: detail.startParam,
        end_param: detail.endParam,
        normal: point(detail.normal),
      };
    case 'SPLINE':
      return {
        type: 'SPLINE',
        degree: Math.min(11, Math.max(1, detail.degree)),
        control_points: points(detail.controlPoints),
        knots: detail.knots,
        weights: detail.weights,
        fit_points: detail.fitPoints ? points(detail.fitPoints) : undefined,
        closed: detail.closed,
      };
    case 'TEXT':
      return {
        type: 'TEXT',
        text: detail.text.normalize('NFC'),
        insert: point(detail.insert),
        align_point: detail.alignPoint ? point(detail.alignPoint) : undefined,
        height_mm: positive(detail.heightMm),
        rotation_deg: detail.rotationDeg,
        width_factor: positive(detail.widthFactor),
        oblique_deg: detail.obliqueDeg,
        style: detail.style,
      };
    case 'MTEXT':
      return {
        type: 'MTEXT',
        raw: detail.raw,
        plain: detail.plain.normalize('NFC'),
        insert: point(detail.insert),
        char_height_mm: positive(detail.charHeightMm),
        width_mm: Math.max(0, detail.widthMm),
        rotation_deg: detail.rotationDeg,
        attachment_point: Math.min(9, Math.max(1, detail.attachmentPoint)),
        line_spacing_factor: positive(detail.lineSpacingFactor),
        style: detail.style,
      };
    case 'ATTRIB':
      return {
        type: 'ATTRIB',
        tag: detail.tag === '' ? '?' : detail.tag,
        text: detail.text.normalize('NFC'),
        insert: point(detail.insert),
        height_mm: positive(detail.heightMm),
        rotation_deg: detail.rotationDeg,
        style: detail.style,
        is_invisible: detail.isInvisible,
      };
    case 'ATTDEF':
      return {
        type: 'ATTDEF',
        tag: detail.tag === '' ? '?' : detail.tag,
        prompt: detail.prompt,
        default_text: detail.defaultText,
        insert: point(detail.insert),
        height_mm: positive(detail.heightMm),
        rotation_deg: detail.rotationDeg,
        style: detail.style,
      };
    case 'INSERT':
      return {
        type: 'INSERT',
        block_name: detail.blockName,
        transform: {
          insert: point(detail.insert),
          scale: detail.scale,
          rotation_deg: detail.rotationDeg,
          normal: point(detail.normal),
          matrix: detail.matrix,
        },
        column_count: detail.columnCount,
        row_count: detail.rowCount,
        column_spacing_mm: detail.columnSpacingMm,
        row_spacing_mm: detail.rowSpacingMm,
      };
    case 'HATCH':
      return {
        type: 'HATCH',
        pattern_name: detail.patternName,
        solid_fill: detail.solidFill,
        pattern_scale: positive(detail.patternScale),
        pattern_angle_deg: detail.patternAngleDeg,
        is_associative: detail.isAssociative,
        boundary_loops: detail.loops.map((loop, index) => ({
          is_outer: index === 0,
          path_kind: 'POLYLINE',
          vertices: points(loop),
        })),
        area_mm2: detail.areaMm2,
      };
    case 'DIMENSION':
      return {
        type: 'DIMENSION',
        dim_kind: detail.dimKind,
        measurement_mm: detail.measurementMm,
        text_override: detail.textOverride,
        text_position: point(detail.textPosition),
        defpoints: points(detail.defpoints),
        dimstyle: detail.dimstyle,
      };
    case 'LEADER':
      return {
        type: 'LEADER',
        vertices: points(detail.vertices),
        has_arrowhead: detail.hasArrowhead,
      };
    case 'MLEADER':
      return {
        type: 'MLEADER',
        leader_lines: detail.leaderLines.map((line) => ({ vertices: points(line) })),
        content_kind: detail.contentKind,
        text_plain: detail.textPlain?.normalize('NFC'),
        block_name: detail.blockName,
      };
    case 'SOLID':
      return { type: 'SOLID', corners: points(detail.corners), area_mm2: detail.areaMm2 };
    case 'POINT':
      return { type: 'POINT', position: point(detail.position) };
    case '3DFACE':
      return {
        type: '3DFACE',
        corners: points(detail.corners),
        invisible_edges: detail.invisibleEdges,
      };
    case 'PROXY':
      return {
        type: 'PROXY',
        original_type: detail.originalType,
        graphics_present: detail.graphicsPresent,
      };
  }
}

/**
 * A HATCH whose loops could not be reconstructed, or an MLEADER with no leader
 * line, cannot satisfy its own branch (`minItems`), so it is downgraded to
 * PROXY rather than emitted invalid. The crosscheck still accounts for it.
 */
function needsDowngrade(detail: CadEntityDetail): boolean {
  if (detail.kind === 'HATCH') return detail.loops.length === 0;
  if (detail.kind === 'MLEADER') return detail.leaderLines.length === 0;
  if (detail.kind === 'LEADER') return detail.vertices.length < 2;
  if (detail.kind === 'SPLINE') return detail.controlPoints.length < 2;
  if (detail.kind === 'LWPOLYLINE' || detail.kind === 'POLYLINE') {
    return detail.vertices.length < 2;
  }
  if (detail.kind === 'SOLID' || detail.kind === '3DFACE') return detail.corners.length < 3;
  return false;
}

function entityOf(entity: CadEntity, file: string): NdjEntity {
  const detail = entity.detail();
  const body = needsDowngrade(detail)
    ? { type: 'PROXY', original_type: entity.dxfType, graphics_present: false }
    : bodyOf(detail);
  if (detail.kind === 'INSERT') {
    // `attribs` denormalises the ATTRIB entities that also appear in the stream
    // under their own handles; the statistics count those, never these copies.
    const attributes = entity.attributes();
    if (attributes.length > 0) {
      body['attribs'] = attributes.map((attribute) => {
        const attributeDetail = attribute.detail();
        return {
          tag: attributeDetail.kind === 'ATTRIB' ? attributeDetail.tag : '?',
          text: attribute.textValue() ?? '',
          provenance: provenanceOf(attribute, file),
        };
      });
    }
  }
  const extents = entity.extents();
  const traits = entity.traits;
  const base: Record<string, unknown> = {
    layer: entity.layer.normalize('NFC'),
    provenance: provenanceOf(entity, file),
    bbox: extents
      ? { min: [extents.min.x, extents.min.y], max: [extents.max.x, extents.max.y] }
      : undefined,
    color: traits.color,
    linetype: traits.linetype,
    lineweight_mm: traits.lineweightMm,
    is_visible: traits.isVisible,
  };
  return compact({ ...base, ...body }) as unknown as NdjEntity;
}

function headerOf(document: CadDocumentHandle, meta: NdjMeta): NdjDocument['header'] {
  const version = document.header.dwgVersion;
  const layouts = document.layouts();
  return compact({
    file_id: meta.file_id,
    file_sha256: meta.file_sha256,
    original_sha256: meta.original_sha256,
    // The enum stops at AC1014; anything older is rejected at import
    // (docs/PLAN.md §5), so an unknown code is reported as the oldest
    // accepted version rather than silently invalidating the document.
    dwg_version: (DWG_VERSIONS.has(version) ? version : 'AC1014') as NdjDocument['header']['dwg_version'],
    codepage_declared: document.header.codepageDeclared,
    codepage_effective: document.header.codepageEffective,
    codepage_override_by_user: document.header.codepageOverrideByUser,
    insunits: Math.min(20, Math.max(0, document.header.insunits)),
    unit_scale_to_mm: meta.unit_scale_to_mm ?? 1,
    producer: {
      name: VIEWER_PRODUCER.name,
      version: meta.producer_version ?? VIEWER_PRODUCER.version,
    },
    layers: document.layers().map((layer) =>
      compact({
        name: layer.name.normalize('NFC'),
        color: layer.color,
        linetype: layer.linetype,
        lineweight_mm: layer.lineweightMm,
        is_off: layer.isOff,
        is_frozen: layer.isFrozen,
        is_locked: layer.isLocked,
        is_plottable: layer.isPlottable,
      })
    ),
    blocks: document
      .blocks()
      .filter((block) => !block.isModelSpace && !block.isPaperSpace)
      .map((block) =>
        compact({
          name: block.name.normalize('NFC'),
          is_xref: block.isXref,
          xref_path: block.xrefPath,
          xref_resolved: block.isXref
            ? block.isUnresolvedXref
              ? ('UNRESOLVED' as const)
              : ('RELATIVE' as const)
            : undefined,
          base_point: point(block.basePoint),
          entity_count: block.entityCount,
          is_anonymous: block.isAnonymous,
        })
      ),
    layouts: layouts.map((layout) =>
      compact({
        name: layout.name.normalize('NFC'),
        is_model: layout.isModel,
        tab_order: layout.tabOrder,
      })
    ),
  }) as NdjDocument['header'];
}

/**
 * Builds the NDJ document. Entities are emitted space by space in the order the
 * database iterates them, with each INSERT immediately followed by its ATTRIBs,
 * so the file is stable for byte-comparison (CLAUDE.md rule 7).
 */
export function exportNdj(document: CadDocumentHandle, meta: NdjMeta): NdjDocument {
  const entities: NdjEntity[] = [];
  for (const view of document.spaces()) {
    for (const entity of view.entities()) {
      entities.push(entityOf(entity, meta.file_sha256));
      for (const attribute of entity.attributes()) {
        entities.push(entityOf(attribute, meta.file_sha256));
      }
    }
  }
  return {
    schema_version: SCHEMA_VERSION,
    header: headerOf(document, meta),
    entities,
  };
}

/** Serialises a document as NDJSON: header line first, then one entity per line. */
export function toNdjsonLines(document: NdjDocument): string {
  const lines = [JSON.stringify({ schema_version: document.schema_version, header: document.header })];
  for (const entity of document.entities) lines.push(JSON.stringify(entity));
  return lines.join('\n') + '\n';
}
