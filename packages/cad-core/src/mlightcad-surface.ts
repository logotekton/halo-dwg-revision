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

import type * as MlightcadViewer from '@mlightcad/cad-simple-viewer';
import type {
  AcApDocManager,
  AcApDocManagerOptions,
  AcApDocument,
  AcApLayerService,
  AcTrView2d,
} from '@mlightcad/cad-simple-viewer';
import type * as MlightcadMTextRenderer from '@mlightcad/mtext-renderer';
import type * as MlightcadThreeRenderer from '@mlightcad/three-renderer';
import {
  AcCmColor,
  AcCmColorMethod,
  AcDbCodePage,
  AcGeBox2d,
  AcGeMatrix3d,
  AcGePoint2d,
  AcGePoint3d,
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
  AcDbDatabaseConverterManager,
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
import type { CadOpenMode, ViewBox, ViewPoint } from './host/types';
import type {
  ViewDocumentEvent,
  ViewEditService,
  ViewOverlayEntity,
  ViewProgressEvent,
  ViewSurface,
  ViewSurfaceOptions,
} from './host/view-surface';
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

  /**
   * `AcDbDatabase.dxfOut()` — the default DWG→DXF converter of ADR-0002
   * (개정 2026-09-02 §1). ASCII output, so the caller can hand it straight to
   * `postProcessDxfOut()`.
   *
   * The signature's first argument is an ObjectARX compatibility leftover and
   * is ignored by the implementation (spike C.7); the file is written by the
   * caller, not here, because this package never touches the file system.
   */
  writeDxf(options: { version?: string; precision?: number } = {}): string {
    const result: unknown = this.db().dxfOut(
      'out.dxf',
      options.precision ?? 6,
      options.version ?? 'AC1032'
    );
    if (typeof result === 'string') return result;
    throw new Error('cad-core: dxfOut did not return ASCII DXF text');
  }

  /** See the exported {@link repairDanglingReferences}. */
  repairDanglingReferences(): DanglingReferenceRepair {
    const database = this.db();
    const blocks = new Set<string>();
    for (const record of database.tables.blockTable.newIterator()) blocks.add(record.name);
    const dimStyles: string[] = [];
    for (const record of database.tables.dimStyleTable.newIterator()) dimStyles.push(record.name);
    const fallbackStyle = dimStyles.includes('Standard') ? 'Standard' : dimStyles[0];
    const names = new Set<string>();
    let droppedInserts = 0;
    let retargetedDimStyles = 0;

    for (const record of database.tables.blockTable.newIterator()) {
      const doomed: AcDbEntity[] = [];
      for (const entity of record.newIterator()) {
        if (entity instanceof AcDbBlockReference) {
          if (blocks.has(entity.blockName)) continue;
          doomed.push(entity);
          names.add(entity.blockName);
          continue;
        }
        if (fallbackStyle === undefined) continue;
        if (entity instanceof AcDbLeader) {
          if (dimStyles.includes(entity.dimensionStyle)) continue;
          names.add(entity.dimensionStyle);
          entity.dimensionStyle = fallbackStyle;
          retargetedDimStyles += 1;
          continue;
        }
        if (entity instanceof AcDbDimension) {
          const style = entity.dimensionStyleName;
          if (style === null || dimStyles.includes(style)) continue;
          names.add(style);
          entity.dimensionStyleName = fallbackStyle;
          retargetedDimStyles += 1;
        }
      }
      for (const entity of doomed) {
        if (entity.erase()) droppedInserts += 1;
      }
    }
    return { droppedInserts, retargetedDimStyles, names: [...names].sort() };
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
 * Serialises an open document back to DXF text with `dxfOut()`.
 *
 * Throws for a handle this module did not create — the facade never lets a
 * caller reach the underlying database, so there is no other way in.
 */
export function writeDxfText(
  document: CadDocumentHandle,
  options: { version?: string; precision?: number } = {}
): string {
  if (!(document instanceof SurfaceDocument)) {
    throw new Error('cad-core: exportDxf needs a handle returned by openDxf/CadHost');
  }
  return document.writeDxf(options);
}

/** What {@link repairDanglingReferences} changed. */
export interface DanglingReferenceRepair {
  /** INSERTs erased because no BLOCK defines their block name. */
  droppedInserts: number;
  /** DIMENSION/LEADER entities re-pointed at an existing dimension style. */
  retargetedDimStyles: number;
  /** The offending names, sorted — for the conversion's warning list. */
  names: string[];
}

/**
 * Repairs references that point at table entries the DWG read did not produce.
 *
 * Both defects below were measured on the real drawing set
 * (`samples/2026-09-02-실시도서`, `01_건축/A-810 천장 평면도.dwg`, AC1024) and
 * neither exists in what acad-ts reads from the same file — acad-ts resolves
 * all 571 INSERTs to 59 real blocks — so they are artefacts of the
 * LibreDWG/data-model path, not of the drawing:
 *
 * 1. **One INSERT names a block `"0"` that no BLOCK record defines.**
 *    `ezdxf.bbox` explodes block references and raises
 *    `DXFStructureError: Required block definition for "0" does not exist`.
 * 2. **LEADER (and DIMENSION) entities name a dimension style `"0"` that the
 *    DIMSTYLE table does not contain.** `ezdxf.bbox` builds a
 *    `DimStyleOverride` per leader and raises `DXFTableEntryError: 0`.
 *
 * Either one makes `halo-engine stats` fail outright, and a failed stats run
 * is a failed conversion under the ADR-0002 개정 §4 gate — the import would
 * fall back to acad-ts for a file the default converter otherwise handles
 * perfectly. The repairs are therefore applied before `dxfOut()` writes, and
 * every change is counted so the conversion reports what it did instead of
 * quietly altering the drawing.
 */
export function repairDanglingReferences(document: CadDocumentHandle): DanglingReferenceRepair {
  if (!(document instanceof SurfaceDocument)) {
    throw new Error('cad-core: repairDanglingReferences needs a handle from openDxf/openDwg');
  }
  return document.repairDanglingReferences();
}

/**
 * Opens DWG bytes. Requires `registerLibreDwgConverter()` from
 * `@halo-cad/dwg-io-gpl` to have run in this realm and therefore a browser-like
 * context with `Worker` (ADR-0002 개정 §2): the converter forces
 * `useWorker: true` and Node has no `Worker` global.
 *
 * The buffer is copied first — the DWG path transfers the input into the
 * parser worker and leaves the caller's `ArrayBuffer` detached (spike C.7).
 */
export async function openDwgDatabase(
  bytes: ArrayBuffer,
  options: { fileSha256?: string } = {}
): Promise<CadDocumentHandle> {
  const copy = bytes.slice(0);
  const database = new AcDbDatabase();
  await database.read(copy, { readOnly: false }, AcDbFileType.DWG);
  const version: unknown = database.version;
  const dwgVersion =
    typeof version === 'object' && version !== null && 'name' in version
      ? String(version.name)
      : 'AC1032';
  const header: CadHeader = {
    dwgVersion,
    codepageDeclared: null,
    codepageEffective: UNICODE_DWG_VERSIONS.has(dwgVersion) ? 'UTF-8' : 'unknown',
    codepageOverrideByUser: false,
    insunits: database.insunits,
  };
  return new SurfaceDocument(database, header, options.fileSha256);
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

// ---------------------------------------------------------------------------
// view surface (W3-02)
// ---------------------------------------------------------------------------

/**
 * The viewer packages are loaded lazily, on the first `createViewSurface()`.
 *
 * `@mlightcad/cad-simple-viewer` reaches for `document` and WebGL at import
 * time, so a static import would break every Node consumer of this package —
 * vitest, `tools/crosscheck/mlightcad-stats.mjs` and the desktop main process
 * all import `openDxf` from the same entry point (spike C.11).
 */
interface ViewerModules {
  viewer: ViewerModule;
  three: ThreeRendererModule;
  fonts: MTextRendererModule;
}

type ViewerModule = typeof MlightcadViewer;
type ThreeRendererModule = typeof MlightcadThreeRenderer;
type MTextRendererModule = typeof MlightcadMTextRenderer;

let viewerModules: Promise<ViewerModules> | null = null;
/**
 * `AcApOpenViewMode` is a runtime enum from the lazily imported viewer bundle,
 * so it is captured when the modules load rather than imported statically —
 * a static import would drag the DOM-dependent viewer into every Node consumer.
 */
let AcApOpenViewMode: ViewerModule['AcApOpenViewMode'];

async function loadViewerModules(): Promise<ViewerModules> {
  viewerModules ??= (async (): Promise<ViewerModules> => {
    const [viewer, three, fonts] = await Promise.all([
      import('@mlightcad/cad-simple-viewer'),
      import('@mlightcad/three-renderer'),
      import('@mlightcad/mtext-renderer'),
    ]);
    return { viewer, three, fonts };
  })();
  return viewerModules;
}

/** `AcEdOpenMode` values, kept as numbers so the enum does not cross the seam. */
const OPEN_MODE: Readonly<Record<CadOpenMode, number>> = { read: 0, review: 4, write: 8 };

/**
 * Worker file names, mirrored from `AcApWorkerAssets` (spike §A).
 *
 * `@halo-cad/dwg-io-gpl` exports the same three constants, but importing that
 * package here would pull a GPL dependency into cad-core (CLAUDE.md rule 3), so
 * the two names the viewer needs are repeated instead. `packages/dwg-io-gpl`'s
 * asset copier is what puts the files on disk under the same names.
 */
const LIBREDWG_PARSER_WORKER_FILE = 'libredwg-parser-worker.js';
const MTEXT_RENDERER_WORKER_FILE = 'mtext-renderer-worker.js';

/** Default Korean fallback chain (spike B.2/B.3); W3-05 owns the manifest. */
const DEFAULT_FONT_CHAIN = ['whgtxt', 'hztxt', 'simsun', 'simplex'];

/** `addTransientEntity()` is fire-and-forget; poll the scene for this long. */
const TRANSIENT_POLL_TIMEOUT_MS = 5_000;
const TRANSIENT_POLL_INTERVAL_MS = 20;

function box2d(box: ViewBox): AcGeBox2d {
  return new AcGeBox2d({ x: box.min.x, y: box.min.y }, { x: box.max.x, y: box.max.y });
}

function colorOfSpec(color: number | string): AcCmColor {
  if (typeof color === 'number') {
    const value = new AcCmColor(AcCmColorMethod.ByACI);
    value.colorIndex = color;
    return value;
  }
  return new AcCmColor(AcCmColorMethod.ByColor).setRGBFromCss(color);
}

function overlayEntity(spec: ViewOverlayEntity): AcDbEntity {
  switch (spec.kind) {
    case 'line':
      return new AcDbLine(
        new AcGePoint3d(spec.start.x, spec.start.y, 0),
        new AcGePoint3d(spec.end.x, spec.end.y, 0)
      );
    case 'polyline': {
      const polyline = new AcDbPolyline();
      spec.points.forEach((point, index) => {
        polyline.addVertexAt(index, new AcGePoint2d(point.x, point.y));
      });
      polyline.closed = spec.closed;
      return polyline;
    }
    case 'circle':
      return new AcDbCircle(new AcGePoint3d(spec.center.x, spec.center.y, 0), spec.radiusMm);
    case 'text': {
      const text = new AcDbText();
      text.textString = spec.text;
      text.position = new AcGePoint3d(spec.position.x, spec.position.y, 0);
      text.height = spec.heightMm;
      return text;
    }
  }
}

/** Finite, inside the ±1e20 sentinel, and not degenerate in x or y. */
function usableExtents(min: { x: number; y: number }, max: { x: number; y: number }): boolean {
  const values = [min.x, min.y, max.x, max.y];
  if (!values.every((value) => Number.isFinite(value) && Math.abs(value) < EXTENTS_SENTINEL)) {
    return false;
  }
  return max.x > min.x && max.y > min.y;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mounts `AcApDocManager` on a DOM container and projects it onto
 * {@link ViewSurface}.
 *
 * Everything version-fragile about the viewer is inside this function: the
 * twelve `AcTrView2d` methods the facade uses, the two `FontManager`s, the
 * five singletons `dispose()` has to unwind, and the event names.
 */
export async function createViewSurface(options: ViewSurfaceOptions): Promise<ViewSurface> {
  const { viewer, three, fonts } = await loadViewerModules();
  AcApOpenViewMode = viewer.AcApOpenViewMode;
  const assetsBaseUrl = options.assetsBaseUrl.replace(/\/+$/, '');
  const workerBaseUrl = `${assetsBaseUrl}/workers`;

  // GPL boundary: the caller injects the registration from
  // `@halo-cad/dwg-io-gpl`; this package never imports libredwg (CLAUDE.md 3).
  options.registerDwgConverter?.(workerBaseUrl);

  const managerOptions: AcApDocManagerOptions = {
    container: options.container,
    autoResize: true,
    // `resolveFontsBaseUrl()` appends `/fonts/`; without this the viewer would
    // fetch from jsdelivr, which CLAUDE.md rule 9 forbids at runtime.
    baseUrl: assetsBaseUrl,
    webworkerFileUrls: {
      mtextRender: `${workerBaseUrl}/${MTEXT_RENDERER_WORKER_FILE}`,
      dwgParser: `${workerBaseUrl}/${LIBREDWG_PARSER_WORKER_FILE}`,
    },
    checkWorkersOnInit: options.checkWorkers,
    builtinOpenFileDialog: false,
  };
  const manager = viewer.AcApDocManager.createInstance(managerOptions);
  if (!manager) throw new Error('cad-core: AcApDocManager.createInstance returned undefined');

  const view = (): AcTrView2d => manager.curView;
  const documentByName = (name: string): AcApDocument | undefined =>
    manager.documents.find((candidate) => candidate.fileName === name);

  const surface = new MlightcadViewSurface(manager, viewer, three, fonts, view, documentByName);
  await surface.setFontChain(options.fontChain ?? DEFAULT_FONT_CHAIN);
  return surface;
}

class MlightcadViewSurface implements ViewSurface {
  private readonly cleanups: (() => void)[] = [];
  private readonly documentListeners = new Set<(event: ViewDocumentEvent) => void>();
  private readonly selectionListeners = new Set<(handles: CadHandle[]) => void>();
  private readonly entityListeners = new Set<
    (handles: CadHandle[], kind: 'append' | 'modify' | 'erase') => void
  >();
  private lastError: string | null = null;
  /** Detaches the entity listeners of the database currently bound. */
  private databaseCleanup: (() => void) | null = null;

  constructor(
    private readonly manager: AcApDocManager,
    private readonly viewer: ViewerModules['viewer'],
    private readonly three: ViewerModules['three'],
    private readonly fonts: ViewerModules['fonts'],
    private readonly view: () => AcTrView2d,
    private readonly documentByName: (name: string) => AcApDocument | undefined
  ) {
    this.wireDocumentEvents();
    this.wireSelectionEvents();
  }

  private wireDocumentEvents(): void {
    const events = this.manager.events;
    const bind = (
      manager: { addEventListener(fn: (payload: { doc: AcApDocument }) => void): void;
        removeEventListener(fn: (payload: { doc: AcApDocument }) => void): void },
      kind: ViewDocumentEvent['kind']
    ): void => {
      const listener = (payload: { doc: AcApDocument }): void => {
        const event: ViewDocumentEvent = { name: payload.doc.fileName, kind };
        for (const callback of this.documentListeners) callback(event);
      };
      manager.addEventListener(listener);
      this.cleanups.push(() => {
        manager.removeEventListener(listener);
      });
    };
    bind(events.documentToBeOpened, 'toBeOpened');
    bind(events.documentCreated, 'created');
    bind(events.documentActivated, 'activated');
    bind(events.documentToBeDestroyed, 'toBeDestroyed');
    bind(events.documentDestroyed, 'destroyed');
  }

  /**
   * The selection set is per view and survives document switches, so listening
   * once on `curView` is enough; both events report the *whole* selection so
   * the facade never has to diff.
   */
  private wireSelectionEvents(): void {
    const selectionSet = this.view().selectionSet;
    const notify = (): void => {
      const handles = [...selectionSet.ids];
      for (const callback of this.selectionListeners) callback(handles);
    };
    selectionSet.events.selectionAdded.addEventListener(notify);
    selectionSet.events.selectionRemoved.addEventListener(notify);
    this.cleanups.push(() => {
      selectionSet.events.selectionAdded.removeEventListener(notify);
      selectionSet.events.selectionRemoved.removeEventListener(notify);
    });
  }

  async workersReady(): Promise<boolean> {
    return this.manager.areWorkersReady();
  }

  async open(name: string, bytes: ArrayBuffer, mode: CadOpenMode): Promise<boolean> {
    // The DWG path transfers the buffer into the parser worker and detaches
    // the caller's copy (spike C.7), so hand the viewer a copy of our own.
    const copy = bytes.slice(0);
    try {
      // `openViewMode` is always `Saved`. `Extents` starts a poller that
      // re-frames the view on a later 300 ms tick (`zoomToFitDrawing`), which
      // would overwrite the fit `CadHost.open()` applies once the scene is
      // idle — measured on F06, where the deferred fit won and left the camera
      // on an empty corner of the sheet. Framing therefore happens in exactly
      // one place: `CadHost.open()`.
      return await this.manager.openDocument(name, copy, {
        mode: OPEN_MODE[mode],
        openViewMode: AcApOpenViewMode.Saved,
        // Convert entities in time-budgeted batches instead of one blocking
        // pass. On the large facility drawings the single-pass conversion of a
        // ~60 MB working DXF pushed the renderer past its heap limit and
        // Chromium killed it; yielding between batches keeps the peak down and
        // lets the first geometry appear while the rest lands.
        progressiveRendering: true,
      });
    } finally {
      this.bindDatabaseEvents();
    }
  }

  /**
   * Rebinds the entity events onto the *current* database.
   *
   * They live on `AcDbDatabase`, which is replaced by every open and close, so
   * the previous binding is released first: keeping the old detach closure
   * around would pin the closed document's whole entity graph and leak one
   * drawing per tab (measured on the 20-document heap test of this task).
   */
  private bindDatabaseEvents(): void {
    this.databaseCleanup?.();
    this.databaseCleanup = this.wireDatabaseEvents(this.manager.curDocument.database);
  }

  private wireDatabaseEvents(database: AcDbDatabase): () => void {
    const emit =
      (kind: 'append' | 'modify' | 'erase') =>
      (payload: { entity: AcDbEntity | AcDbEntity[] }): void => {
        const entities = Array.isArray(payload.entity) ? payload.entity : [payload.entity];
        const handles = entities.map((entity) => entity.objectId);
        if (handles.length === 0) return;
        for (const callback of this.entityListeners) callback(handles, kind);
      };
    const appended = emit('append');
    const modified = emit('modify');
    const erased = emit('erase');
    database.events.entityAppended.addEventListener(appended);
    database.events.entityModified.addEventListener(modified);
    database.events.entityErased.addEventListener(erased);
    return (): void => {
      database.events.entityAppended.removeEventListener(appended);
      database.events.entityModified.removeEventListener(modified);
      database.events.entityErased.removeEventListener(erased);
    };
  }

  async activate(name: string): Promise<boolean> {
    const document = this.documentByName(name);
    if (!document) return false;
    return this.manager.activateDocument(document);
  }

  async close(name: string): Promise<boolean> {
    const document = this.documentByName(name);
    if (!document) return false;
    try {
      return await this.manager.closeDocument(document);
    } finally {
      // Closing swaps `curDocument` (the last close is replaced by a fresh
      // Untitled document — spike C.10), so the entity events move with it.
      this.bindDatabaseEvents();
    }
  }

  documentNames(): string[] {
    return this.manager.documents.map((document) => document.fileName);
  }

  activeDocumentName(): string | null {
    return this.manager.curDocument.fileName || null;
  }

  documentHandle(): CadDocumentHandle | null {
    const database = this.manager.curDocument.database;
    const version: unknown = database.version;
    const dwgVersion =
      typeof version === 'object' && version !== null && 'name' in version
        ? String(version.name)
        : 'AC1032';
    const header: CadHeader = {
      dwgVersion,
      codepageDeclared: null,
      codepageEffective: UNICODE_DWG_VERSIONS.has(dwgVersion) ? 'UTF-8' : 'unknown',
      codepageOverrideByUser: false,
      insunits: database.insunits,
    };
    return new SurfaceDocument(database, header, undefined);
  }

  entityCount(): number {
    let count = 0;
    const database = this.manager.curDocument.database;
    for (const record of database.tables.blockTable.newIterator()) {
      if (!record.isModelSapce && !record.isPaperSapce) continue;
      count += record.newIterator().count;
    }
    return count;
  }

  layers(): CadLayer[] {
    return this.documentHandle()?.layers() ?? [];
  }

  /**
   * Layer visibility, through the viewer's own layer service.
   *
   * Not by assigning `record.isOff` on a record read out of the layer table:
   * the renderer only repaints when `AcDbDatabase.events.layerModified` fires,
   * and that event comes from the write transaction
   * (`AcApLayerService.setLayerOn` → `acapRunServiceEdit`), not from the
   * setter. The service also resolves the layer by *name* through
   * `AcDbLayerTable.getAt`, which matters on real drawings: a layer and a text
   * style can share an object id, and a lookup by id then edits the wrong
   * record and silently does nothing (`AcApLayerService.openLayerForWrite`).
   *
   * `isFrozen` is deliberately not used for this: its setter in 1.14.3 ORs the
   * flag in and can never clear it (`AcDbLayerTableRecord.isFrozen`), so a
   * frozen layer could not be thawed again. Off/on is the reversible switch,
   * and it is the one `docs/contracts/compare-dxf.md` §9 asks for.
   */
  setLayerVisible(name: string, visible: boolean): boolean {
    const service = this.layerService();
    if (!service) return false;
    // `switchCurrentLayer: false`: this is a viewer toggle, not an edit
    // session; moving CLAYER because the user hid a layer would be a surprise.
    return service.setLayerOn(name, visible, { switchCurrentLayer: false });
  }

  setLayersVisible(entries: Record<string, boolean>): string[] {
    const service = this.layerService();
    if (!service) return [];
    const known = new Set(this.layers().map((layer) => layer.name));
    const on: string[] = [];
    const off: string[] = [];
    // Sorted so a batch is deterministic regardless of key insertion order
    // (CLAUDE.md rule 6).
    for (const name of Object.keys(entries).sort()) {
      if (!known.has(name)) continue;
      (entries[name] === true ? on : off).push(name);
    }
    // Two transactions, one repaint: `layerModified` only marks the view dirty
    // and the paint happens on the next animation frame, so both halves land in
    // the same frame. `skipCurrentLayer: false` because the caller named the
    // layers explicitly — the compare layers are never CLAYER, and silently
    // skipping one would leave the view in a state `layers()` does not report.
    if (off.length > 0) service.setLayersVisibility(off, true, { skipCurrentLayer: false });
    if (on.length > 0) service.setLayersVisibility(on, false, { skipCurrentLayer: false });
    return [...on, ...off].sort();
  }

  /** The active document's layer service, or null when nothing is open. */
  private layerService(): AcApLayerService | null {
    const document: AcApDocument | undefined = this.manager.curDocument;
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- defensive: `curDocument` is typed as always present but is undefined before the first open in 1.6.3
    return document ? document.layerService : null;
  }

  layouts(): CadLayout[] {
    return this.documentHandle()?.layouts() ?? [];
  }

  activeLayoutHandle(): string | null {
    return this.view().activeLayoutBtrId || null;
  }

  setActiveLayout(blockRecordHandle: string): boolean {
    const known = this.layouts().some((layout) => layout.blockRecordHandle === blockRecordHandle);
    if (!known) return false;
    this.view().activeLayoutBtrId = blockRecordHandle;
    return true;
  }

  async waitUntilIdle(timeoutMs: number): Promise<boolean> {
    return this.view().waitUntilIdle(timeoutMs);
  }

  async nextFrame(timeoutMs: number): Promise<boolean> {
    const events = this.view().events.renderFrame;
    return new Promise<boolean>((resolve) => {
      let done = false;
      const finish = (painted: boolean): void => {
        if (done) return;
        done = true;
        events.removeEventListener(listener);
        clearTimeout(timer);
        resolve(painted);
      };
      const listener = (): void => {
        finish(true);
      };
      const timer = setTimeout(() => {
        finish(false);
      }, timeoutMs);
      events.addEventListener(listener);
    });
  }

  regen(): void {
    this.manager.regen();
  }

  pick(worldPoint: ViewPoint, hitRadiusPx: number): CadHandle[] {
    return this.view()
      .pick({ x: worldPoint.x, y: worldPoint.y }, hitRadiusPx)
      .map((item) => item.id);
  }

  search(box: ViewBox): CadHandle[] {
    return this.view()
      .search(box2d(box))
      .map((item) => item.id);
  }

  selectByBox(
    box: ViewBox,
    mode: 'window' | 'crossing',
    action: 'replace' | 'add' | 'remove'
  ): void {
    this.view().selectByBoxWithMode(box2d(box), mode, action);
  }

  setSelection(handles: CadHandle[]): void {
    const selectionSet = this.view().selectionSet;
    selectionSet.clear();
    if (handles.length > 0) selectionSet.add(handles);
  }

  selection(): CadHandle[] {
    return [...this.view().selectionSet.ids];
  }

  highlight(handles: CadHandle[]): void {
    this.view().highlight(handles);
  }

  unhighlight(handles: CadHandle[]): void {
    this.view().unhighlight(handles);
  }

  zoomTo(box: ViewBox, margin?: number): void {
    this.view().zoomTo(box2d(box), margin);
  }

  /**
   * Frames the whole drawing.
   *
   * `zoomToFitDrawing()` is not enough on its own: it starts a poller that
   * checks `isProcessingEntities` **every 300 ms** and applies the fit only on
   * a later tick, so a caller that renders or screenshots straight afterwards
   * still sees the previous camera (measured on F06). When the file carries
   * usable `$EXTMIN`/`$EXTMAX` the box is therefore applied directly, which is
   * both immediate and deterministic; the poller stays as the fallback for
   * files whose header extents are missing or degenerate.
   */
  zoomToFit(timeoutMs?: number): void {
    const view = this.view();
    const box = this.drawingExtents();
    if (box) {
      view.zoomTo(box2d(box), 1.05);
      return;
    }
    view.zoomToFitDrawing(timeoutMs);
  }

  /**
   * The box to frame, in drawing units.
   *
   * First choice is the scene's own bounding box (`AcTrScene.box`): it covers
   * exactly the geometry that was converted, which is what the user is about
   * to look at, and it is ready as soon as the scene is idle. The header's
   * `$EXTMIN`/`$EXTMAX` are the fallback — and often useless: both
   * `fixtures/generated/F06.dxf` and its `dxfOut()` conversion carry the ±1e20
   * "no extents" sentinel. `null` means neither is usable.
   */
  private drawingExtents(): ViewBox | null {
    // `AcTrScene.box` is a `THREE.Box3`; three's types are not part of this
    // package's program (only mlightcad's are), so the value arrives untyped
    // and is narrowed to the two vectors that are read.
    const sceneBox = this.view().cadScene.box as unknown as
      | { min: Vec3; max: Vec3 }
      | undefined;
    if (sceneBox && usableExtents(sceneBox.min, sceneBox.max)) {
      return {
        min: { x: sceneBox.min.x, y: sceneBox.min.y },
        max: { x: sceneBox.max.x, y: sceneBox.max.y },
      };
    }
    const database = this.manager.curDocument.database;
    const min = database.extmin;
    const max = database.extmax;
    if (!usableExtents(min, max)) return null;
    return { min: { x: min.x, y: min.y }, max: { x: max.x, y: max.y } };
  }

  zoomToLayer(layerName: string): boolean {
    return this.view().zoomToFitLayer(layerName);
  }

  screenToWorld(point: ViewPoint): ViewPoint {
    const world = this.view().screenToWorld(new AcGePoint2d(point.x, point.y));
    return { x: world.x, y: world.y };
  }

  worldToScreen(point: ViewPoint): ViewPoint {
    const screen = this.view().worldToScreen(new AcGePoint2d(point.x, point.y));
    return { x: screen.x, y: screen.y };
  }

  /**
   * Adds transient entities and waits until the scene really has them.
   *
   * `AcTrView2d.addTransientEntity()` returns void and finishes drawing later
   * (spike C.5); `AcTrScene.setTransientEntityVisible()` is the only published
   * predicate that reports whether an object arrived, so it doubles as the
   * completion signal here.
   */
  async addTransient(
    entities: ViewOverlayEntity[],
    color: number | string,
    layer: string
  ): Promise<CadHandle[]> {
    if (entities.length === 0) return [];
    const view = this.view();
    const colorValue = colorOfSpec(color);
    const created = entities.map((spec) => {
      const entity = overlayEntity(spec);
      entity.layer = layer;
      entity.color = colorValue;
      return entity;
    });
    view.addTransientEntity(created);
    const handles = created.map((entity) => entity.objectId);
    const deadline = Date.now() + TRANSIENT_POLL_TIMEOUT_MS;
    for (;;) {
      const ready = handles.every((handle) => view.cadScene.setTransientEntityVisible(handle, true));
      if (ready || Date.now() > deadline) break;
      await delay(TRANSIENT_POLL_INTERVAL_MS);
    }
    return handles;
  }

  setTransientVisible(handles: CadHandle[], visible: boolean): boolean {
    const scene = this.view().cadScene;
    let ok = handles.length > 0;
    for (const handle of handles) {
      if (!scene.setTransientEntityVisible(handle, visible)) ok = false;
    }
    return ok;
  }

  removeTransient(handles: CadHandle[]): void {
    const view = this.view();
    for (const handle of handles) view.removeTransientEntity(handle);
  }

  async runCommand(name: string, script?: string[]): Promise<void> {
    const lines = [name, ...(script ?? [])];
    await this.manager.executeCommandString(lines.join('\n'));
  }

  runEdit<T>(label: string, fn: (service: ViewEditService) => T): T {
    const document = this.manager.curDocument;
    const service = document.entityService;
    const database = document.database;
    let result!: T;
    this.viewer.acapRunDatabaseEdit(database, label, () => {
      result = fn({
        erase: (handles) => service.eraseEntities(handles),
        move: (handles, displacement) =>
          service.translateEntities(service.getEntitiesByIds(handles), {
            x: displacement.x,
            y: displacement.y,
            z: 0,
          }),
        rotate: (handles, basePoint, angleDeg) =>
          service.rotateEntities(
            service.getEntitiesByIds(handles),
            { x: basePoint.x, y: basePoint.y, z: 0 },
            (angleDeg * Math.PI) / 180
          ),
        copy: (handles, displacement) => {
          const matrix = new AcGeMatrix3d().makeTranslation(displacement.x, displacement.y, 0);
          const clones = service.cloneAndTransform(service.getEntitiesByIds(handles), matrix, {
            append: true,
          });
          return clones.map((entity) => entity.objectId);
        },
      });
    });
    return result;
  }

  undo(): boolean {
    return this.manager.curDocument.database.transactionManager.undo();
  }

  redo(): boolean {
    return this.manager.curDocument.database.transactionManager.redo();
  }

  canUndo(): boolean {
    return this.manager.curDocument.database.transactionManager.canUndo();
  }

  canRedo(): boolean {
    return this.manager.curDocument.database.transactionManager.canRedo();
  }

  /**
   * Pushes the fallback chain through **both** font managers.
   *
   * MTEXT is laid out in the mtext-renderer worker, which owns its own
   * `FontManager`; the main-thread instance does not reach it and
   * `AcTrMTextRenderer.getInstance().setDefaultFonts()` is the only public
   * channel that does (spike B.3, trap 1).
   */
  async setFontChain(chain: string[]): Promise<void> {
    const manager = this.fonts.FontManager.instance;
    manager.setDefaultFonts(chain);
    try {
      await manager.loadFontsByNames(chain);
      await this.three.AcTrMTextRenderer.getInstance().setDefaultFonts(chain);
      await this.manager.loadDefaultFonts(chain);
    } catch {
      // A missing font file is reported through `fonts-not-found` and shown by
      // the missing-font panel (W3-05); it must not fail the whole mount.
    }
  }

  missingFonts(): string[] {
    return Object.keys(this.view().missedData.fonts);
  }

  unresolvedXrefs(): { name: string; path: string; isOverlay: boolean }[] {
    return this.view().missedData.xrefs.map((xref) => ({
      name: xref.name,
      path: xref.pathName,
      isOverlay: xref.isOverlay,
    }));
  }

  onDocument(callback: (event: ViewDocumentEvent) => void): () => void {
    this.documentListeners.add(callback);
    return () => {
      this.documentListeners.delete(callback);
    };
  }

  onSelection(callback: (handles: CadHandle[]) => void): () => void {
    this.selectionListeners.add(callback);
    return () => {
      this.selectionListeners.delete(callback);
    };
  }

  onEntityChanged(
    callback: (handles: CadHandle[], kind: 'append' | 'modify' | 'erase') => void
  ): () => void {
    this.entityListeners.add(callback);
    return () => {
      this.entityListeners.delete(callback);
    };
  }

  onUndoStack(callback: () => void): () => void {
    const listener = (): void => {
      callback();
    };
    this.viewer.eventBus.on('undo-stack-changed', listener);
    return () => {
      this.viewer.eventBus.off('undo-stack-changed', listener);
    };
  }

  onProgress(callback: (event: ViewProgressEvent) => void): () => void {
    const listener = (payload: { percentage: number; stage: unknown }): void => {
      callback({ percentage: payload.percentage, stage: String(payload.stage) });
    };
    this.viewer.eventBus.on('open-file-progress', listener);
    return () => {
      this.viewer.eventBus.off('open-file-progress', listener);
    };
  }

  onOpenFailed(callback: (message: string) => void): () => void {
    const listener = (payload: { fileName: string; errorMessage?: string }): void => {
      this.lastError = payload.errorMessage ?? payload.fileName;
      callback(this.lastError);
    };
    this.viewer.eventBus.on('failed-to-open-file', listener);
    return () => {
      this.viewer.eventBus.off('failed-to-open-file', listener);
    };
  }

  onMissedData(callback: () => void): () => void {
    const listener = (): void => {
      callback();
    };
    this.viewer.eventBus.on('missed-data-changed', listener);
    return () => {
      this.viewer.eventBus.off('missed-data-changed', listener);
    };
  }

  /**
   * Unwinds all five singletons the proposal lists
   * (`AcApDocManager`, `AcDbDatabaseConverterManager`, `AcApXrefManager`,
   * `FontManager`, `AcTrMTextRenderer`). Anything that throws on the way out is
   * swallowed: a half-disposed viewer must not keep the next mount from
   * starting, and the heap test measures the result, not the path.
   */
  async dispose(): Promise<void> {
    this.databaseCleanup?.();
    this.databaseCleanup = null;
    for (const cleanup of this.cleanups.splice(0)) {
      try {
        cleanup();
      } catch {
        // listener already detached
      }
    }
    this.documentListeners.clear();
    this.selectionListeners.clear();
    this.entityListeners.clear();
    const steps: (() => unknown)[] = [
      (): void => {
        this.view().stopAnimationLoop();
      },
      (): void => {
        this.view().clear();
      },
      (): Promise<void> => this.manager.destroy(),
      (): void => {
        this.viewer.AcApXrefManager.instance.clearAll();
      },
      (): void => {
        AcDbDatabaseConverterManager.instance.unregister(AcDbFileType.DWG);
      },
      (): void => {
        this.three.AcTrMTextRenderer.getInstance().dispose();
      },
      (): void => {
        this.three.AcTrMTextRenderer.resetInstance();
      },
    ];
    for (const step of steps) {
      try {
        await step();
      } catch {
        // best effort teardown
      }
    }
  }
}
