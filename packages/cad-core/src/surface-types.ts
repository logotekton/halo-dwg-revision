/**
 * mlightcad-free view of a CAD database.
 *
 * `mlightcad-surface.ts` is the only file in this package allowed to import the
 * mlightcad packages (CLAUDE.md rule "packages/cad-core: mlightcad 유일 임포트").
 * The name is deliberately not spelled out anywhere else in `src/`, because the
 * W2-02 acceptance check greps for it across the whole directory.
 * Everything downstream — `stats.ts`, `ndj.ts`, `index.ts` — works against the
 * plain interfaces declared here, so no mlightcad class, enum or geometry type
 * can leak into the package's public API or into `apps/**`.
 *
 * The shapes are deliberately dumb: numbers, strings and plain records. Heavy
 * geometry (spline control points, hatch loops, polyline vertices) sits behind
 * {@link CadEntity.detail}, which is only called by the NDJ exporter, so layer
 * statistics never pay for it.
 */

/** DXF handle, uppercase hexadecimal, no `0x` prefix. */
export type CadHandle = string;

/** `MODEL`, or `PAPER:<layout name>` (see `common/primitives.schema.json`). */
export type CadSpace = string;

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface CadExtents {
  min: Vec3;
  max: Vec3;
}

/**
 * The two public routes to a curve length measured by the W1-04 spike
 * (`docs/spikes/mlightcad-api.md` C.2). `AcDbCurve` has no `length` getter.
 *
 * - `intersect-curves` sums the `AcGeIntersectPrimitive` lengths returned by
 *   `subGetIntersectCurves()`. Available for every curve.
 * - `entity-properties` reads the computed `geometry.length` entry of the
 *   property-inspector schema. Only LINE, LWPOLYLINE, POLYLINE and ELLIPSE
 *   publish it in 1.14.3; the others return `null`.
 */
export type CurveLengthPath = 'intersect-curves' | 'entity-properties';

/** Normalised entity type: the closed `entity_type` enum of `ndj/entity.schema.json`. */
export type NdjEntityType =
  | 'LINE'
  | 'LWPOLYLINE'
  | 'POLYLINE'
  | 'ARC'
  | 'CIRCLE'
  | 'ELLIPSE'
  | 'SPLINE'
  | 'TEXT'
  | 'MTEXT'
  | 'ATTRIB'
  | 'ATTDEF'
  | 'INSERT'
  | 'HATCH'
  | 'DIMENSION'
  | 'LEADER'
  | 'MLEADER'
  | 'SOLID'
  | 'POINT'
  | '3DFACE'
  | 'PROXY';

export interface CadHeader {
  /** `$ACADVER`, e.g. `AC1032`. */
  dwgVersion: string;
  /** `$DWGCODEPAGE` exactly as written in the file, `null` when absent. */
  codepageDeclared: string | null;
  /** Codepage actually used to decode strings. `UTF-8` for R2007+. */
  codepageEffective: string;
  /** True when the caller forced the encoding through `openDxf(bytes, { encoding })`. */
  codepageOverrideByUser: boolean;
  /** `$INSUNITS` (0 unitless, 4 mm, 5 cm, 6 m). */
  insunits: number;
}

export interface CadLayer {
  name: string;
  /** ACI index, or `#RRGGBB` for a true colour. */
  color: number | string | undefined;
  linetype: string | undefined;
  /** Plot lineweight in mm, or the DXF sentinels -1 BYLAYER / -2 BYBLOCK / -3 DEFAULT. */
  lineweightMm: number | undefined;
  isOff: boolean;
  isFrozen: boolean;
  isLocked: boolean;
  isPlottable: boolean;
}

export interface CadBlock {
  name: string;
  handle: CadHandle;
  isXref: boolean;
  isUnresolvedXref: boolean;
  /** Path stored in the drawing for an external reference, before resolution. */
  xrefPath: string | undefined;
  basePoint: Vec3;
  entityCount: number;
  isAnonymous: boolean;
  isModelSpace: boolean;
  isPaperSpace: boolean;
}

export interface CadLayout {
  name: string;
  isModel: boolean;
  tabOrder: number;
  blockRecordHandle: CadHandle;
}

/** Entity graphical traits shared by every NDJ branch (`entity.schema.json` `base`). */
export interface CadTraits {
  /** ACI index 0..256, or `#RRGGBB`. */
  color: number | string | undefined;
  linetype: string | undefined;
  lineweightMm: number | undefined;
  isVisible: boolean;
}

export interface CadPolylineVertex {
  x: number;
  y: number;
  bulge: number;
}

/**
 * Full geometry payload for the NDJ exporter, one variant per normalised type.
 * Produced lazily by {@link CadEntity.detail}.
 */
export type CadEntityDetail =
  | { kind: 'LINE'; start: Vec3; end: Vec3 }
  | {
      kind: 'LWPOLYLINE';
      vertices: CadPolylineVertex[];
      closed: boolean;
      elevationMm: number;
    }
  | {
      kind: 'POLYLINE';
      polylineKind: '2D' | '3D' | 'MESH' | 'PFACE';
      vertices: CadPolylineVertex[];
      closed: boolean;
    }
  | {
      kind: 'ARC';
      center: Vec3;
      radiusMm: number;
      startAngleDeg: number;
      endAngleDeg: number;
      normal: Vec3;
    }
  | { kind: 'CIRCLE'; center: Vec3; radiusMm: number; normal: Vec3 }
  | {
      kind: 'ELLIPSE';
      center: Vec3;
      majorAxis: Vec3;
      ratio: number;
      startParam: number;
      endParam: number;
      normal: Vec3;
    }
  | {
      kind: 'SPLINE';
      degree: number;
      controlPoints: Vec3[];
      knots: number[];
      weights: number[] | undefined;
      fitPoints: Vec3[] | undefined;
      closed: boolean;
    }
  | {
      kind: 'TEXT';
      text: string;
      insert: Vec3;
      alignPoint: Vec3 | undefined;
      heightMm: number;
      rotationDeg: number;
      widthFactor: number;
      obliqueDeg: number;
      style: string | undefined;
    }
  | {
      kind: 'MTEXT';
      raw: string;
      plain: string;
      insert: Vec3;
      charHeightMm: number;
      widthMm: number;
      rotationDeg: number;
      attachmentPoint: number;
      lineSpacingFactor: number;
      style: string | undefined;
    }
  | {
      kind: 'ATTRIB';
      tag: string;
      text: string;
      insert: Vec3;
      heightMm: number;
      rotationDeg: number;
      style: string | undefined;
      isInvisible: boolean;
    }
  | {
      kind: 'ATTDEF';
      tag: string;
      prompt: string | undefined;
      defaultText: string | undefined;
      insert: Vec3;
      heightMm: number;
      rotationDeg: number;
      style: string | undefined;
    }
  | {
      kind: 'INSERT';
      blockName: string;
      insert: Vec3;
      scale: [number, number, number];
      rotationDeg: number;
      normal: Vec3;
      /** Row-major 4x4 block transform. */
      matrix: number[];
      columnCount: number;
      rowCount: number;
      columnSpacingMm: number;
      rowSpacingMm: number;
    }
  | {
      kind: 'HATCH';
      patternName: string;
      solidFill: boolean;
      patternScale: number;
      patternAngleDeg: number;
      isAssociative: boolean;
      /** Tessellated boundary loops; index 0 is the outer loop. */
      loops: Vec3[][];
      areaMm2: number;
    }
  | {
      kind: 'DIMENSION';
      dimKind:
        | 'LINEAR'
        | 'ALIGNED'
        | 'ANGULAR'
        | 'ANGULAR_3P'
        | 'DIAMETER'
        | 'RADIUS'
        | 'ORDINATE'
        | 'ARC_LENGTH';
      measurementMm: number;
      textOverride: string | undefined;
      textPosition: Vec3;
      defpoints: Vec3[];
      dimstyle: string | undefined;
    }
  | { kind: 'LEADER'; vertices: Vec3[]; hasArrowhead: boolean }
  | {
      kind: 'MLEADER';
      leaderLines: Vec3[][];
      contentKind: 'MTEXT' | 'BLOCK' | 'NONE';
      textPlain: string | undefined;
      blockName: string | undefined;
    }
  | { kind: 'SOLID'; corners: Vec3[]; areaMm2: number }
  | { kind: 'POINT'; position: Vec3 }
  | { kind: '3DFACE'; corners: Vec3[]; invisibleEdges: number }
  | { kind: 'PROXY'; originalType: string; graphicsPresent: boolean };

/**
 * One top-level entity of a space, or one ATTRIB owned by a block reference.
 *
 * All getters are cheap except {@link detail}; `curveLength` and `extents`
 * delegate to mlightcad geometry and are memoised by the caller when needed.
 */
export interface CadEntity {
  readonly handle: CadHandle;
  /**
   * `provenance.file` / `EntityRef.file` for this entity: the sha256 handed to
   * `openDxf`, or `undefined` when the document was opened without one.
   */
  readonly file: string | undefined;
  /** DXF record name exactly as reported by mlightcad (`dxfTypeName`). */
  readonly dxfType: string;
  /** {@link dxfType} mapped onto the closed NDJ enum; unknown types become `PROXY`. */
  readonly type: NdjEntityType;
  readonly layer: string;
  readonly space: CadSpace;
  /** INSERT chain from the top-level owner down to (but not including) `handle`. */
  readonly path: CadHandle[];
  readonly traits: CadTraits;
  extents(): CadExtents | null;
  /**
   * Curve length in mm per `docs/contracts/stats-definition.md`.
   * Returns `null` when the requested path cannot measure this entity,
   * and `0` for an entity that is not a curve.
   */
  curveLength(path?: CurveLengthPath): number | null;
  /** Net HATCH area (outer minus holes) in mm², `null` for other types. */
  hatchArea(): number | null;
  /** Text contributed to `text_count` / `text_hash`, `null` for non-text entities. */
  textValue(): string | null;
  /** Block name for INSERT, `null` otherwise. */
  blockName(): string | null;
  /** ATTRIBs owned by this INSERT; empty for everything else. */
  attributes(): CadEntity[];
  detail(): CadEntityDetail;
}

export interface CadSpaceView {
  readonly space: CadSpace;
  readonly blockRecordHandle: CadHandle;
  entities(): Iterable<CadEntity>;
}

/**
 * Handle returned by `openDxf`. Opaque to callers: they pass it back to
 * `statsByLayer`, `exportNdj` and `dispose`.
 */
export interface CadDocumentHandle {
  readonly header: CadHeader;
  readonly fileSha256: string | undefined;
  layers(): CadLayer[];
  blocks(): CadBlock[];
  layouts(): CadLayout[];
  /** Model space first, then paper-space layouts in tab order. */
  spaces(): CadSpaceView[];
  readonly disposed: boolean;
}
