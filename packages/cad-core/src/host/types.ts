/**
 * The public vocabulary of {@link CadHost}. Plain data only — no mlightcad
 * type reaches this far (`docs/dev/cadhost-proposal.md`, CLAUDE.md
 * "packages/cad-core: mlightcad 유일 임포트").
 */

import type { CadHandle, CadLayer, CadLayout } from '../surface-types';

/** A point in drawing (world) coordinates, millimetres. */
export interface ViewPoint {
  x: number;
  y: number;
}

/** An axis-aligned rectangle in world coordinates. */
export interface ViewBox {
  min: ViewPoint;
  max: ViewPoint;
}

/** Access mode a document is opened with (`AcEdOpenMode`). */
export type CadOpenMode = 'read' | 'review' | 'write';

/** Where the whole host is in its lifecycle; mirrors the `viewer` store's `status`. */
export type CadHostStatus = 'idle' | 'opening' | 'rendering' | 'ready' | 'failed';

/** Large-drawing tier of ADR-0002 개정 §5. */
export type EntityTier = 'A' | 'B' | 'C';

export type OverlayId = string;

/**
 * One transient overlay entity. Deliberately a small, closed set: overlays
 * carry evidence, diff and crosscheck marks, not drawing content.
 */
export type OverlayEntitySpec =
  | { kind: 'line'; start: ViewPoint; end: ViewPoint }
  | { kind: 'polyline'; points: ViewPoint[]; closed?: boolean }
  | { kind: 'rect'; box: ViewBox }
  | { kind: 'circle'; center: ViewPoint; radiusMm: number }
  | { kind: 'text'; position: ViewPoint; text: string; heightMm?: number };

/** A group of transient entities added and removed as one unit. */
export interface OverlayJson {
  /** Caller-chosen id; generated when omitted. */
  id?: OverlayId;
  /** ACI colour index (1–255) or `#RRGGBB`. Default 1 (red). */
  color?: number | string;
  /** Layer the transient entities claim. Default `HALO-OVERLAY`. */
  layer?: string;
  entities: OverlayEntitySpec[];
}

/** What `open()` reports back to the renderer. */
export interface OpenResult {
  fileId: string;
  name: string;
  entityCount: number;
  layers: number;
  layouts: number;
  tier: EntityTier;
  /** Machine-readable warnings; the renderer maps `i18nKey` onto `ko.json`. */
  warnings: CadHostWarning[];
  /** Wall-clock time from `open()` to render idle, milliseconds. */
  durationMs: number;
  /** False when the render did not settle inside the timeout. */
  renderIdle: boolean;
}

/**
 * A warning the host raises. Korean text lives in `apps/web/src/i18n/ko.json`
 * under the key named here (CLAUDE.md rule 8) — the host never carries UI
 * strings.
 */
export interface CadHostWarning {
  code: 'tier-b' | 'tier-c' | 'tier-changed' | 'render-timeout' | 'fonts-missing' | 'xref-unresolved';
  i18nKey: string;
  /** Interpolation values for the message, e.g. `{ count: 250000 }`. */
  params?: Record<string, string | number>;
}

/** Progress of an open, forwarded from `AcDbDatabase.events.openProgress`. */
export interface OpenProgress {
  fileId: string;
  /** 0–100 where the source provides it. */
  percentage: number;
  stage: string;
  warnings: CadHostWarning[];
}

/** The edit surface handed to `CadHost.edit()`. */
export interface CadEditTx {
  /** Erases entities; returns how many were removed. */
  erase(handles: CadHandle[]): number;
  /** Moves entities by a displacement in millimetres. */
  move(handles: CadHandle[], displacement: ViewPoint): number;
  /** Rotates entities around `basePoint`, degrees counter-clockwise. */
  rotate(handles: CadHandle[], basePoint: ViewPoint, angleDeg: number): number;
  /** Copies entities by a displacement; returns the new handles. */
  copy(handles: CadHandle[], displacement: ViewPoint): CadHandle[];
}

export interface CadHostEventMap {
  selectionChanged: { handles: CadHandle[] };
  documentOpened: OpenResult;
  documentActivated: { fileId: string };
  documentClosed: { fileId: string };
  renderIdle: { fileId: string; durationMs: number };
  undoStackChanged: { canUndo: boolean; canRedo: boolean };
  entityChanged: { handles: CadHandle[]; kind: 'append' | 'modify' | 'erase' };
  fontMissing: { fonts: string[] };
  xrefUnresolved: { name: string; path: string; isOverlay: boolean }[];
  openProgress: OpenProgress;
  openFailed: { fileId: string; message: string };
  statusChanged: { status: CadHostStatus };
}

export type CadHostEvent = keyof CadHostEventMap;

export interface CadHostOptions {
  /** The `#viewer-root` element (`docs/contracts/wave-3.md` "렌더러 상태"). */
  container: HTMLElement;
  /**
   * Root the viewer assets were deployed under, no trailing slash — in the
   * desktop app `halocad://app/viewer`, from `window.halocad.viewer.assetsBase()`.
   * `workers/` and `fonts/` hang off it.
   */
  assetsBaseUrl: string;
  /** Default open mode for documents. Default `'write'`. */
  mode?: CadOpenMode;
  /**
   * Font fallback chain pushed into both the main-thread `FontManager` and the
   * MTEXT worker pool (spike B.3). Default: the Korean chain.
   */
  fontChain?: string[];
  /**
   * Called once during `create()` with `${assetsBaseUrl}/workers` so the caller
   * can register the GPL DWG converter from `@halo-cad/dwg-io-gpl`. Left unset,
   * DWG bytes cannot be opened — which is the correct default everywhere except
   * the hidden converter window (CLAUDE.md rule 3).
   */
  registerDwgConverter?: (workerBaseUrl: string) => void;
  /** HEAD-probe the worker URLs at start-up (`checkWorkersOnInit`). Default true. */
  checkWorkers?: boolean;
  /** How long `open()` waits for the render to settle. Default 60 000 ms. */
  renderTimeoutMs?: number;
}

export type { CadHandle, CadLayer, CadLayout };
