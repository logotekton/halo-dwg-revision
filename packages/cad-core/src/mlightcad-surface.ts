/**
 * The **only** file in `@halo-cad/cad-core` that may import `@mlightcad/*`.
 *
 * Everything the rest of the package (and everything downstream) needs from
 * mlightcad is projected here onto the plain interfaces of `surface-types.ts`.
 * The rule is enforced by `no-restricted-imports` in this package's
 * `eslint.config.mjs` and re-checked by grep in the acceptance commands of
 * `docs/briefs/W2-02.md`.
 *
 * Facts used here were measured by the W1-04 spike; section references point at
 * `docs/spikes/mlightcad-api.md`.
 */

import type { AcApDocManagerOptions } from '@mlightcad/cad-simple-viewer';
import {
  AcDbCodePage,
  AcDb2dPolyline,
  AcDb3PointAngularDimension,
  AcDbAlignedDimension,
  AcDbArc,
  AcDbArcDimension,
  AcDbAttribute,
  AcDbAttributeDefinition,
  AcDbBlockReference,
  AcDbCircle,
  AcDbCurve,
  AcDbDatabase,
  AcDbDiametricDimension,
  AcDbDimension,
  AcDbEllipse,
  AcDbFace,
  AcDbFileType,
  AcDbHatch,
  AcDbLeader,
  AcDbLine,
  AcDbMLeader,
  AcDbMText,
  AcDbOrdinateDimension,
  AcDbPoint,
  AcDbPolyline,
  AcDbProxyEntity,
  AcDbRadialDimension,
  AcDbSolid,
  AcDbSpline,
  AcDbText,
  acdbDwgCodePageToEncoding,
} from '@mlightcad/data-model';
import type { AcDbEntity } from '@mlightcad/data-model';

import {
  fitPointSplineLength,
  nurbsFromControlPoints,
  nurbsLength,
  scanSplineFitData,
} from './curve-length';
import type { SplineFitData } from './curve-length';
import type {
  CadBlock,
  CadDocumentHandle,
  CadEntity,
  CadEntityDetail,
  CadExtents,
  CadHandle,
  CadHeader,
  CadLayer,
  CadLayout,
  CadPolylineVertex,
  CadSpace,
  CadSpaceView,
  CadTraits,
  CurveLengthPath,
  NdjEntityType,
  Vec3,
} from './surface-types';

/**
 * Options W3-02 will hand to `AcApDocManager.createInstance`. Declared here so
 * the type-only dependency on `@mlightcad/cad-simple-viewer` is exercised by
 * `tsc` in this task already — it is the dependency whose broken `.d.ts` files
 * force `skipLibCheck: true` (ADR-0006, spike D.1). Not re-exported from
 * `src/index.ts`: the public API stays free of mlightcad types.
 */
export type ViewHostOptions = AcApDocManagerOptions;

/** DXF version codes that carry UTF-8 regardless of `$DWGCODEPAGE` (R2007+). */
const UNICODE_DWG_VERSIONS = new Set(['AC1021', 'AC1024', 'AC1027', 'AC1032']);

/**
 * `dxfTypeName` values that map onto a different NDJ `entity_type`. Everything
 * not in {@link NDJ_TYPES} after this rewrite becomes `PROXY`.
 */
const TYPE_ALIASES: Readonly<Record<string, NdjEntityType>> = {
  MULTILEADER: 'MLEADER',
  TRACE: 'SOLID',
};

const NDJ_TYPES: ReadonlySet<string> = new Set<NdjEntityType>([
  'LINE',
  'LWPOLYLINE',
  'POLYLINE',
  'ARC',
  'CIRCLE',
  'ELLIPSE',
  'SPLINE',
  'TEXT',
  'MTEXT',
  'ATTRIB',
  'ATTDEF',
  'INSERT',
  'HATCH',
  'DIMENSION',
  'LEADER',
  'MLEADER',
  'SOLID',
  'POINT',
  '3DFACE',
  'PROXY',
]);

/** Types whose length is summed into `length_sum_mm` (stats contract, table row 2). */
const LENGTH_TYPES: ReadonlySet<NdjEntityType> = new Set<NdjEntityType>([
  'LINE',
  'LWPOLYLINE',
  'POLYLINE',
  'ARC',
  'CIRCLE',
  'ELLIPSE',
  'SPLINE',
]);

const RAD_TO_DEG = 180 / Math.PI;

/** `AcGeBox3d` uses ±1e20 as the "no extents" sentinel. */
const EXTENTS_SENTINEL = 1e19;

export function normaliseEntityType(dxfTypeName: string): NdjEntityType {
  const aliased = TYPE_ALIASES[dxfTypeName];
  if (aliased) return aliased;
  return NDJ_TYPES.has(dxfTypeName) ? (dxfTypeName as NdjEntityType) : 'PROXY';
}

function vec(point: { x: number; y: number; z?: number } | undefined): Vec3 {
  if (!point) return { x: 0, y: 0, z: 0 };
  return { x: point.x, y: point.y, z: point.z ?? 0 };
}

function colorOf(color: {
  isByLayer: boolean;
  isByBlock: boolean;
  isByACI: boolean;
  colorIndex: number | undefined;
  hexColor: string | undefined;
}): number | string | undefined {
  if (color.isByLayer) return 256;
  if (color.isByBlock) return 0;
  if (color.isByACI && color.colorIndex !== undefined) return color.colorIndex;
  const hex = color.hexColor;
  if (hex === undefined) return undefined;
  return hex.startsWith('#') ? hex.toUpperCase() : `#${hex.toUpperCase()}`;
}

/**
 * DXF stores plot lineweight in 1/100 mm; -1 BYLAYER, -2 BYBLOCK, -3 DEFAULT
 * are sentinels the NDJ schema keeps verbatim.
 */
function lineweightMm(raw: number | undefined): number | undefined {
  if (raw === undefined) return undefined;
  return raw < 0 ? raw : raw / 100;
}

/**
 * Reads `$ACADVER` / `$DWGCODEPAGE` straight out of the file bytes.
 *
 * `AcDbDatabase` exposes `version` but not the declared code page, and the NDJ
 * header needs both (`ndj/document.schema.json` header). Only the first 64 KiB
 * are scanned: the HEADER section always comes first in a DXF and both
 * variables sit near its top. Bytes are read as latin-1 so a CP949 payload
 * further down the file can never break the scan.
 */
function readHeaderVariables(bytes: ArrayBuffer): {
  acadver: string | null;
  codepage: string | null;
} {
  const view = new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 64 * 1024));
  let text = '';
  // Chunked to stay clear of the argument-count limit on String.fromCharCode.
  for (let offset = 0; offset < view.length; offset += 4096) {
    text += String.fromCharCode(...view.subarray(offset, offset + 4096));
  }
  const pick = (name: string): string | null => {
    const at = text.indexOf(name);
    if (at < 0) return null;
    // `$ACADVER\n  1\nAC1032` — the group code line then the value line.
    const rest = text.slice(at + name.length);
    const lines = rest.split(/\r?\n/);
    return lines[2]?.trim() ?? null;
  };
  return { acadver: pick('$ACADVER'), codepage: pick('$DWGCODEPAGE') };
}

function effectiveEncoding(
  dwgVersion: string,
  declared: string | null,
  override: string | undefined
): string {
  if (override !== undefined && override !== '') return override;
  if (UNICODE_DWG_VERSIONS.has(dwgVersion)) return 'UTF-8';
  if (declared === null) return 'UTF-8';
  // `AcDbCodePage` is a numeric enum keyed by the `$DWGCODEPAGE` spelling
  // (`ANSI_949` → 40) and `acdbDwgCodePageToEncoding` maps that number onto a
  // WHATWG encoding label (`euc-kr`). A code page outside the enum falls back
  // to the declared string so the header still says what the file said.
  const code: unknown = (AcDbCodePage as unknown as Record<string, number | undefined>)[declared];
  if (typeof code !== 'number') return declared;
  const mapped: unknown = acdbDwgCodePageToEncoding(code);
  return typeof mapped === 'string' && mapped.length > 0 ? mapped : declared;
}

/** MTEXT control codes stripped for the `plain` field of `ndj/entity.schema.json`. */
export function mtextToPlain(contents: string): string {
  return contents
    .replace(/\\P/g, '\n')
    .replace(/\\~/g, ' ')
    .replace(/\\[LlOoKk]/g, '')
    .replace(/\\[fF][^;]*;/g, '')
    .replace(/\\[HhWwQqTtAaCc][^;\\]*;/g, '')
    .replace(/\\S([^;]*);/g, (_all: string, stacked: string) => stacked.replace(/[#^\\]/g, '/'))
    .replace(/[{}]/g, '')
    .replace(/\\(.)/g, '$1');
}

// ---------------------------------------------------------------------------
// curve length
// ---------------------------------------------------------------------------

interface LengthCarrier {
  length?: number;
}

/**
 * Sums the intersect primitives of a curve (spike C.2 route (a)).
 * `AcGeIntersectPrimitive` is a union keyed by `kind`; every member exposes
 * a `length` on its geometry object.
 */
function lengthFromIntersectCurves(entity: AcDbEntity): number {
  if (!(entity instanceof AcDbCurve)) return 0;
  let total = 0;
  for (const primitive of entity.subGetIntersectCurves()) {
    const carrier: LengthCarrier | undefined =
      'line' in primitive
        ? primitive.line
        : 'arc' in primitive
          ? primitive.arc
          : 'spline' in primitive
            ? primitive.spline
            : undefined;
    if (carrier && typeof carrier.length === 'number') total += carrier.length;
  }
  return total;
}

/**
 * SPLINE length by our own NURBS flattening (`curve-length.ts`) instead of
 * `AcGeSpline3d.length`.
 *
 * Two different corrections hide behind one call:
 *
 * 1. **Fit-point splines.** `AcDbSpline.fromDwgSpline` turns DXF groups
 *    11/21/31 into control points with a *uniform* parametrisation, while
 *    AutoCAD, BricsCAD and ezdxf use chord parametrisation with natural knots.
 *    The two curves pass through the same points and differ in between — on
 *    F01 by +11.3%, the gap that whitelist W01 covered. `splineFits` carries
 *    the fit points read straight from the file, so the curve is rebuilt the
 *    way the engine builds it.
 * 2. **Control-point splines.** The stored control points are exact, and here
 *    mlightcad's own `length` already agrees with flattening to 3e-5%; going
 *    through the same code path anyway removes the dependency on an
 *    implementation detail of a pinned version.
 *
 * Falls back to the intersect-curve sum when neither route produces a curve.
 */
function splineLength(entity: AcDbEntity, fit: SplineFitData | undefined): number {
  if (fit) {
    const fromFitPoints = fitPointSplineLength(fit);
    if (fromFitPoints !== null) return fromFitPoints;
  }
  const geo = readGeo<SplineGeo>(entity);
  if (geo) {
    const curve = nurbsFromControlPoints({
      degree: geo.degree,
      controlPoints: geo.controlPoints.map(vec),
      knots: geo.knots,
      ...(geo.weights ? { weights: geo.weights } : {}),
    });
    if (curve) return nurbsLength(curve);
  }
  return lengthFromIntersectCurves(entity);
}

/**
 * Reads the computed `geometry.length` of the property-inspector schema
 * (spike C.2 route (b)). Returns `null` when the entity does not publish it —
 * measured in 1.14.3: ARC, CIRCLE and SPLINE do not.
 */
function lengthFromProperties(entity: AcDbEntity): number | null {
  const groups = entity.properties.groups;
  const geometry = groups.find((group) => group.groupName === 'geometry');
  const property = geometry?.properties.find((candidate) => candidate.name === 'length');
  if (!property) return null;
  const value: unknown = property.accessor.get();
  return typeof value === 'number' ? value : null;
}

// ---------------------------------------------------------------------------
// entity detail
// ---------------------------------------------------------------------------

/**
 * `AcDbSpline` keeps its NURBS data on the private `_geo` field: 1.14.3 has no
 * public getter for degree / control points / knots (checked against
 * `lib/entity/AcDbSpline.d.ts`). The same applies to `AcDbHatch._geo`, an
 * `AcGeArea2d` whose `loops` and `tessellate()` *are* public. Reaching for the
 * field is contained in this file and guarded by `readGeo`; a future release
 * that renames it degrades to an empty payload instead of throwing.
 */
interface SplineGeo {
  degree: number;
  controlPoints: { x: number; y: number; z?: number }[];
  knots: number[];
  weights?: number[];
  fitPoints?: { x: number; y: number; z?: number }[];
  closed: boolean;
}

interface AreaGeo {
  loops: readonly unknown[];
  tessellate(): { x: number; y: number }[][];
}

// eslint-disable-next-line @typescript-eslint/no-unnecessary-type-parameters -- callers name the geometry type they expect
function readGeo<T>(entity: object): T | null {
  const geo: unknown = (entity as { _geo?: unknown })._geo;
  return geo == null ? null : (geo as T);
}

/** DXF group 70 of DIMENSION: low three bits are the kind, the rest are flags. */
function dimensionKind(entity: AcDbDimension): CadEntityDetail & { kind: 'DIMENSION' } {
  const defpoints: Vec3[] = [];
  let dimKind: (CadEntityDetail & { kind: 'DIMENSION' })['dimKind'] = 'LINEAR';
  if (entity instanceof AcDb3PointAngularDimension || entity instanceof AcDbArcDimension) {
    dimKind = entity instanceof AcDbArcDimension ? 'ARC_LENGTH' : 'ANGULAR_3P';
    defpoints.push(vec(entity.centerPoint), vec(entity.xLine1Point), vec(entity.xLine2Point), vec(entity.arcPoint));
  } else if (entity instanceof AcDbRadialDimension) {
    dimKind = 'RADIUS';
    defpoints.push(vec(entity.center), vec(entity.chordPoint));
  } else if (entity instanceof AcDbDiametricDimension) {
    dimKind = 'DIAMETER';
    defpoints.push(vec(entity.chordPoint), vec(entity.farChordPoint));
  } else if (entity instanceof AcDbOrdinateDimension) {
    dimKind = 'ORDINATE';
    defpoints.push(vec(entity.definingPoint), vec(entity.leaderEndPoint));
  } else if (entity instanceof AcDbAlignedDimension) {
    // AcDbRotatedDimension extends AcDbAlignedDimension; bit 0 of group 70
    // separates rotated (0) from aligned (1).
    dimKind = (entity.dimensionType & 7) === 1 ? 'ALIGNED' : 'LINEAR';
    defpoints.push(vec(entity.dimLinePoint), vec(entity.xLine1Point), vec(entity.xLine2Point));
  } else {
    defpoints.push(vec(entity.dimBlockPosition));
  }
  const text = entity.dimensionText;
  return {
    kind: 'DIMENSION',
    dimKind,
    // 1.14.3 leaves `measurement` undefined for every DXF-read dimension
    // (group 42 is optional and ezdxf omits it); the crosscheck does not use
    // it, so 0 is recorded rather than a guess. See the W2-02 report.
    measurementMm: entity.measurement ?? 0,
    textOverride: text === null || text === '' ? undefined : text,
    textPosition: vec(entity.textPosition),
    defpoints: defpoints.length > 0 ? defpoints : [vec(entity.dimBlockPosition)],
    dimstyle: entity.dimensionStyleName ?? undefined,
  };
}

function polylineVertices(entity: AcDbPolyline): CadPolylineVertex[] {
  const bulges = polylineBulges(entity);
  const out: CadPolylineVertex[] = [];
  for (let index = 0; index < entity.numberOfVertices; index += 1) {
    const point = entity.getPoint2dAt(index);
    out.push({ x: point.x, y: point.y, bulge: bulges[index] ?? 0 });
  }
  return out;
}

/**
 * `AcDbPolyline` has `getPoint2dAt` but no public bulge getter; the property
 * inspector's `geometry.vertices` array carries `{x, y, bulge, …}` records.
 */
function polylineBulges(entity: AcDbPolyline): number[] {
  const geometry = entity.properties.groups.find((group) => group.groupName === 'geometry');
  const vertices = geometry?.properties.find((property) => property.name === 'vertices');
  const value: unknown = vertices?.accessor.get();
  if (!Array.isArray(value)) return [];
  return value.map((item) => {
    const bulge: unknown = (item as { bulge?: unknown }).bulge;
    return typeof bulge === 'number' ? bulge : 0;
  });
}

function mleaderDetail(entity: AcDbMLeader): CadEntityDetail {
  const leaderLines: Vec3[][] = [];
  for (const leader of entity.leaders) {
    for (const line of leader.leaderLines) {
      const points = line.vertices.map(vec);
      const last = leader.lastLeaderLinePoint;
      if (last) {
        const tail = vec(last);
        const previous = points[points.length - 1];
        const samePoint =
          previous !== undefined
            ? previous.x === tail.x && previous.y === tail.y && previous.z === tail.z
            : false;
        if (!samePoint) {
          points.push(tail);
        }
      }
      if (points.length >= 2) leaderLines.push(points);
    }
  }
  const textGroup = entity.properties.groups.find((group) => group.groupName === 'text');
  const contents: unknown = textGroup?.properties
    .find((property) => property.name === 'contents')
    ?.accessor.get();
  const contentType: number = entity.contentType;
  const contentKind = contentType === 1 ? 'BLOCK' : contentType === 2 ? 'MTEXT' : 'NONE';
  return {
    kind: 'MLEADER',
    leaderLines:
      leaderLines.length > 0 ? leaderLines : [[vec(entity.doglegVector), vec(entity.landingPoint)]],
    contentKind,
    textPlain: typeof contents === 'string' ? mtextToPlain(contents) : undefined,
    blockName: undefined,
  };
}

function detailOf(entity: AcDbEntity): CadEntityDetail {
  if (entity instanceof AcDbLine) {
    return { kind: 'LINE', start: vec(entity.startPoint), end: vec(entity.endPoint) };
  }
  if (entity instanceof AcDbPolyline) {
    return {
      kind: 'LWPOLYLINE',
      vertices: polylineVertices(entity),
      closed: entity.closed,
      elevationMm: entity.elevation,
    };
  }
  if (entity instanceof AcDb2dPolyline) {
    const vertices: CadPolylineVertex[] = [];
    for (let index = 0; index < entity.numberOfVertices; index += 1) {
      const point = entity.getPointAt(index);
      vertices.push({ x: point.x, y: point.y, bulge: entity.getBulgeAt(index) });
    }
    return { kind: 'POLYLINE', polylineKind: '2D', vertices, closed: entity.closed };
  }
  if (entity instanceof AcDbArc) {
    return {
      kind: 'ARC',
      center: vec(entity.center),
      radiusMm: entity.radius,
      startAngleDeg: entity.startAngle * RAD_TO_DEG,
      endAngleDeg: entity.endAngle * RAD_TO_DEG,
      normal: vec(entity.normal),
    };
  }
  if (entity instanceof AcDbCircle) {
    return {
      kind: 'CIRCLE',
      center: vec(entity.center),
      radiusMm: entity.radius,
      normal: vec(entity.normal),
    };
  }
  if (entity instanceof AcDbEllipse) {
    const axis = vec(entity.majorAxis);
    const radius = entity.majorAxisRadius;
    return {
      kind: 'ELLIPSE',
      center: vec(entity.center),
      majorAxis: { x: axis.x * radius, y: axis.y * radius, z: axis.z * radius },
      ratio: radius === 0 ? 1 : Math.min(1, entity.minorAxisRadius / radius),
      startParam: entity.startAngle,
      endParam: entity.endAngle,
      normal: vec(entity.normal),
    };
  }
  if (entity instanceof AcDbSpline) {
    const geo = readGeo<SplineGeo>(entity);
    return {
      kind: 'SPLINE',
      degree: geo?.degree ?? 3,
      controlPoints: (geo?.controlPoints ?? []).map(vec),
      knots: geo?.knots ?? [],
      weights: geo?.weights,
      fitPoints: geo?.fitPoints?.map(vec),
      closed: geo?.closed ?? entity.closed,
    };
  }
  if (entity instanceof AcDbAttribute) {
    return {
      kind: 'ATTRIB',
      tag: entity.tag,
      text: entity.textString,
      insert: vec(entity.position),
      heightMm: entity.height,
      rotationDeg: entity.rotation * RAD_TO_DEG,
      style: entity.styleName,
      isInvisible: entity.isInvisible,
    };
  }
  if (entity instanceof AcDbAttributeDefinition) {
    return {
      kind: 'ATTDEF',
      tag: entity.tag,
      prompt: entity.prompt,
      defaultText: entity.textString,
      insert: vec(entity.position),
      heightMm: entity.height,
      rotationDeg: entity.rotation * RAD_TO_DEG,
      style: entity.styleName,
    };
  }
  if (entity instanceof AcDbText) {
    const alignment = vec(entity.alignmentPoint);
    const hasAlignment = alignment.x !== 0 || alignment.y !== 0 || alignment.z !== 0;
    return {
      kind: 'TEXT',
      text: entity.textString,
      insert: vec(entity.position),
      alignPoint: hasAlignment ? alignment : undefined,
      heightMm: entity.height,
      rotationDeg: entity.rotation * RAD_TO_DEG,
      widthFactor: entity.widthFactor,
      obliqueDeg: entity.oblique * RAD_TO_DEG,
      style: entity.styleName,
    };
  }
  if (entity instanceof AcDbMText) {
    return {
      kind: 'MTEXT',
      raw: entity.contents,
      plain: mtextToPlain(entity.contents),
      insert: vec(entity.location),
      charHeightMm: entity.height,
      widthMm: entity.width,
      rotationDeg: entity.rotation * RAD_TO_DEG,
      attachmentPoint: entity.attachmentPoint,
      lineSpacingFactor: entity.lineSpacingFactor,
      style: entity.styleName,
    };
  }
  if (entity instanceof AcDbBlockReference) {
    // `blockTransform.elements` is column-major 4x4 (spike C.1); the schema
    // documents `matrix` as row-major, so it is transposed here.
    const columnMajor = entity.blockTransform.elements;
    const rowMajor: number[] = [];
    for (let row = 0; row < 4; row += 1) {
      for (let column = 0; column < 4; column += 1) {
        rowMajor.push(columnMajor[column * 4 + row] ?? 0);
      }
    }
    const scale = entity.scaleFactors;
    return {
      kind: 'INSERT',
      blockName: entity.blockName,
      insert: vec(entity.position),
      scale: [scale.x, scale.y, scale.z],
      rotationDeg: entity.rotation * RAD_TO_DEG,
      normal: vec(entity.normal),
      matrix: rowMajor,
      columnCount: Math.max(1, entity.columnCount),
      rowCount: Math.max(1, entity.rowCount),
      columnSpacingMm: entity.columnSpacing,
      rowSpacingMm: entity.rowSpacing,
    };
  }
  if (entity instanceof AcDbHatch) {
    const geo = readGeo<AreaGeo>(entity);
    let loops: Vec3[][] = [];
    if (geo) {
      loops = geo
        .tessellate()
        .map((loop) => loop.map((point) => ({ x: point.x, y: point.y, z: entity.elevation })))
        .filter((loop) => loop.length >= 3);
    }
    return {
      kind: 'HATCH',
      patternName: entity.patternName === '' ? 'SOLID' : entity.patternName,
      solidFill: entity.isSolidFill,
      patternScale: entity.patternScale,
      patternAngleDeg: entity.patternAngle * RAD_TO_DEG,
      isAssociative: entity.associative,
      loops,
      areaMm2: Math.abs(entity.area),
    };
  }
  if (entity instanceof AcDbDimension) return dimensionKind(entity);
  if (entity instanceof AcDbLeader) {
    return {
      kind: 'LEADER',
      vertices: entity.vertices.map(vec),
      hasArrowhead: entity.hasArrowHead,
    };
  }
  if (entity instanceof AcDbMLeader) return mleaderDetail(entity);
  if (entity instanceof AcDbSolid) {
    // DXF stores SOLID corners with the third and fourth swapped; the schema
    // asks for drawing order, so they are unswapped here.
    const corners = [0, 1, 3, 2].map((index) => vec(entity.getPointAt(index)));
    return { kind: 'SOLID', corners, areaMm2: Math.abs(entity.area) };
  }
  if (entity instanceof AcDbFace) {
    const corners = [0, 1, 2, 3].map((index) => vec(entity.getVertexAt(index)));
    let invisibleEdges = 0;
    for (let index = 0; index < 4; index += 1) {
      if (!entity.isEdgeVisibleAt(index)) invisibleEdges |= 1 << index;
    }
    return { kind: '3DFACE', corners, invisibleEdges };
  }
  if (entity instanceof AcDbPoint) {
    return { kind: 'POINT', position: vec(entity.position) };
  }
  if (entity instanceof AcDbProxyEntity) {
    return {
      kind: 'PROXY',
      originalType: entity.originalDxfName === '' ? entity.dxfTypeName : entity.originalDxfName,
      graphicsPresent: entity.proxyGraphic !== undefined,
    };
  }
  // Anything with no branch above (VIEWPORT, WIPEOUT, MLINE, ACAD_TABLE, …)
  // is reported as PROXY carrying its original DXF name, which is exactly what
  // `ndj/entity.schema.json` reserves the PROXY branch for.
  return { kind: 'PROXY', originalType: entity.dxfTypeName, graphicsPresent: false };
}

// ---------------------------------------------------------------------------
// entity view
// ---------------------------------------------------------------------------

class SurfaceEntity implements CadEntity {
  readonly handle: CadHandle;
  readonly dxfType: string;
  readonly type: NdjEntityType;
  readonly layer: string;
  readonly space: CadSpace;
  readonly path: CadHandle[];

  constructor(
    private readonly entity: AcDbEntity,
    space: CadSpace,
    path: CadHandle[],
    readonly file: string | undefined,
    private readonly splineFits: ReadonlyMap<string, SplineFitData> = new Map()
  ) {
    this.handle = entity.objectId;
    this.dxfType = entity.dxfTypeName;
    this.type = normaliseEntityType(entity.dxfTypeName);
    this.layer = entity.layer;
    this.space = space;
    this.path = path;
  }

  get traits(): CadTraits {
    const entity = this.entity;
    return {
      color: colorOf(entity.color),
      linetype: entity.lineType,
      lineweightMm: lineweightMm(entity.lineWeight),
      isVisible: entity.visibility,
    };
  }

  extents(): CadExtents | null {
    let box: { min: Vec3; max: Vec3 };
    try {
      box = this.entity.geometricExtents;
    } catch {
      return null;
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- defensive: geometricExtents can be undefined for degenerate entities in 1.14.3
    if (!box?.min || !box.max) return null;
    if (!Number.isFinite(box.min.x) || Math.abs(box.min.x) > EXTENTS_SENTINEL) return null;
    if (!Number.isFinite(box.max.x) || Math.abs(box.max.x) > EXTENTS_SENTINEL) return null;
    return { min: vec(box.min), max: vec(box.max) };
  }

  curveLength(path: CurveLengthPath = 'intersect-curves'): number | null {
    if (!LENGTH_TYPES.has(this.type)) return 0;
    if (path === 'entity-properties') return lengthFromProperties(this.entity);
    if (this.type === 'SPLINE') {
      return splineLength(this.entity, this.splineFits.get(this.handle.toUpperCase()));
    }
    return lengthFromIntersectCurves(this.entity);
  }

  hatchArea(): number | null {
    return this.entity instanceof AcDbHatch ? Math.abs(this.entity.area) : null;
  }

  textValue(): string | null {
    const entity = this.entity;
    // AcDbAttribute extends AcDbText, so the ATTRIB branch has to come first.
    if (entity instanceof AcDbAttribute) return entity.textString;
    if (entity instanceof AcDbAttributeDefinition) return null;
    if (entity instanceof AcDbText) return entity.textString;
    // MTEXT hashes the raw contents, control codes included (stats contract).
    if (entity instanceof AcDbMText) return entity.contents;
    return null;
  }

  blockName(): string | null {
    return this.entity instanceof AcDbBlockReference ? this.entity.blockName : null;
  }

  attributes(): CadEntity[] {
    const entity = this.entity;
    if (!(entity instanceof AcDbBlockReference)) return [];
    const out: CadEntity[] = [];
    for (const attribute of entity.attributeIterator()) {
      out.push(
        new SurfaceEntity(
          attribute,
          this.space,
          [...this.path, this.handle],
          this.file,
          this.splineFits
        )
      );
    }
    return out;
  }

  detail(): CadEntityDetail {
    return detailOf(this.entity);
  }
}

// ---------------------------------------------------------------------------
// document handle
// ---------------------------------------------------------------------------

class SurfaceDocument implements CadDocumentHandle {
  disposed = false;

  constructor(
    private database: AcDbDatabase | null,
    readonly header: CadHeader,
    readonly fileSha256: string | undefined,
    private readonly splineFits: ReadonlyMap<string, SplineFitData> = new Map()
  ) {}

  private db(): AcDbDatabase {
    if (!this.database) throw new Error('cad-core: document handle has been disposed');
    return this.database;
  }

  layers(): CadLayer[] {
    const out: CadLayer[] = [];
    for (const record of this.db().tables.layerTable.newIterator()) {
      out.push({
        name: record.name,
        color: colorOf(record.color),
        linetype: record.linetype,
        lineweightMm: lineweightMm(record.lineWeight),
        isOff: record.isOff,
        isFrozen: record.isFrozen,
        isLocked: record.isLocked,
        isPlottable: record.isPlottable,
      });
    }
    return out;
  }

  blocks(): CadBlock[] {
    const out: CadBlock[] = [];
    for (const record of this.db().tables.blockTable.newIterator()) {
      const path = record.pathName;
      out.push({
        name: record.name,
        handle: record.objectId,
        isXref: record.isXref,
        isUnresolvedXref: record.isUnresolvedXref,
        xrefPath: path === '' ? undefined : path,
        basePoint: vec(record.origin),
        entityCount: record.newIterator().count,
        isAnonymous: record.name.startsWith('*'),
        isModelSpace: record.isModelSapce,
        isPaperSpace: record.isPaperSapce,
      });
    }
    return out;
  }

  layouts(): CadLayout[] {
    const out: CadLayout[] = [];
    for (const layout of this.db().objects.layout.newIterator()) {
      out.push({
        name: layout.layoutName,
        isModel: layout.tabOrder === 0,
        tabOrder: layout.tabOrder,
        blockRecordHandle: layout.blockTableRecordId,
      });
    }
    out.sort((left, right) => left.tabOrder - right.tabOrder);
    return out;
  }

  /**
   * Space naming follows the stats contract: `ownerId` → BlockTableRecord, and
   * the record's layout name (not `*Paper_Space`) forms `PAPER:<layout>`.
   * `AcDbEntity` keeps DXF group 67 private, so the owner record is the only
   * reliable discriminator (spike C.1).
   */
  spaces(): CadSpaceView[] {
    const database = this.db();
    const layoutNames = new Map<string, string>();
    for (const layout of database.objects.layout.newIterator()) {
      layoutNames.set(layout.blockTableRecordId, layout.layoutName);
    }
    const model: CadSpaceView[] = [];
    const paper: { view: CadSpaceView; order: number }[] = [];
    for (const record of database.tables.blockTable.newIterator()) {
      const isModel = record.isModelSapce;
      if (!isModel && !record.isPaperSapce) continue;
      const name = layoutNames.get(record.objectId) ?? record.name;
      const space: CadSpace = isModel ? 'MODEL' : `PAPER:${name}`;
      const view: CadSpaceView = {
        space,
        blockRecordHandle: record.objectId,
        entities: () => iterateSpace(record, space, this.fileSha256, this.splineFits),
      };
      if (isModel) model.push(view);
      else paper.push({ view, order: paper.length });
    }
    return [...model, ...paper.map((entry) => entry.view)];
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    // `AcDbDatabase` has no public teardown in 1.14.3 — `clear()` is private and
    // the only published disposer is `AcApDocManager.destroy()`, which needs the
    // viewer. Dropping the single reference this handle holds makes the whole
    // entity graph collectable, and every later call throws instead of walking
    // a database the caller believes is gone. W3-02 adds the viewer-side
    // singleton teardown on top of this (see README, "Disposal").
    this.database = null;
  }
}

function* iterateSpace(
  record: { newIterator(): Iterable<AcDbEntity> },
  space: CadSpace,
  file: string | undefined,
  splineFits: ReadonlyMap<string, SplineFitData>
): Iterable<CadEntity> {
  for (const entity of record.newIterator()) {
    yield new SurfaceEntity(entity, space, [], file, splineFits);
  }
}

export function disposeDocument(document: CadDocumentHandle): void {
  if (document instanceof SurfaceDocument) document.dispose();
}

/**
 * Opens DXF bytes with `AcDbDatabase` directly.
 *
 * The viewer singleton `AcApDocManager` is deliberately not used (brief
 * "Defaults for ambiguity"): it needs a DOM and WebGL, while everything this
 * package does must run headless in vitest.
 *
 * The input buffer is copied first. The DWG path transfers the buffer into the
 * parser worker and leaves the caller's copy detached (spike C.7); copying
 * keeps `openDxf` safe to call with a buffer the caller still owns.
 */
export async function openDxfDatabase(
  bytes: ArrayBuffer,
  options: { encoding?: string; fileSha256?: string } = {}
): Promise<CadDocumentHandle> {
  const copy = bytes.slice(0);
  const { acadver, codepage } = readHeaderVariables(copy);
  // One extra pass over the bytes before the parser runs: data-model discards
  // SPLINE fit points while reading, and `curveLength` needs them to rebuild
  // the curve the way ezdxf does (see `splineLength`). The pass is byte-level
  // and allocates only for the SPLINE records it finds.
  const splineFits = scanSplineFitData(copy);
  const database = new AcDbDatabase();
  await database.read(copy, { readOnly: true }, AcDbFileType.DXF);
  const version: unknown = database.version;
  const dwgVersion =
    typeof version === 'object' && version !== null && 'name' in version
      ? String(version.name)
      : (acadver ?? 'AC1032');
  const header: CadHeader = {
    dwgVersion,
    codepageDeclared: codepage,
    codepageEffective: effectiveEncoding(dwgVersion, codepage, options.encoding),
    codepageOverrideByUser: options.encoding !== undefined && options.encoding !== '',
    insunits: database.insunits,
  };
  return new SurfaceDocument(database, header, options.fileSha256, splineFits);
}
