/**
 * The parts of the host that do not need a browser: the document state
 * machine, the entity-count tiers of ADR-0002 개정 §5, and the facade wired to
 * a stub {@link ViewSurface}.
 *
 * The stub is deliberately faithful about the two measured quirks the machine
 * exists for: `documentCreated` arriving *after* `documentActivated`, and the
 * absence of a render-finished event.
 */

import { describe, expect, it, vi } from 'vitest';

import { CadHost } from '../src/host/cad-host';
import { DocumentStateMachine } from '../src/host/state-machine';
import {
  DWG_BYTES_PER_ENTITY,
  DXF_BYTES_PER_ENTITY,
  estimateEntityTier,
  tierChangeWarnings,
  tierOf,
} from '../src/host/tier';
import type { ViewBox } from '../src/host/types';
import type { ViewDocumentEvent, ViewSurface } from '../src/host/view-surface';
import type { CadHandle, CadLayer } from '../src/surface-types';

// ---------------------------------------------------------------------------
// state machine
// ---------------------------------------------------------------------------

describe('DocumentStateMachine', () => {
  it('does not move a document backwards when documentCreated arrives late', () => {
    const machine = new DocumentStateMachine();
    machine.begin('f1', 'plan.dxf');
    machine.signal('f1', 'toBeOpened');
    machine.signal('f1', 'activated');
    machine.beginRender('f1');
    machine.renderIdle('f1');
    expect(machine.get('f1')?.state).toBe('ready');

    // The spike measured documentCreated 1.2 s after documentActivated.
    machine.signal('f1', 'created');
    expect(machine.get('f1')?.state).toBe('ready');
  });

  it('treats activated as parsed even when created never arrives', () => {
    const machine = new DocumentStateMachine();
    machine.begin('f1', 'plan.dxf');
    machine.signal('f1', 'activated');
    expect(machine.get('f1')?.state).toBe('parsed');
    expect(machine.active()).toBe('f1');
  });

  it('keeps tab order and moves the active document on close', () => {
    const machine = new DocumentStateMachine();
    machine.begin('a', 'a.dxf');
    machine.begin('b', 'b.dxf');
    machine.begin('c', 'c.dxf');
    machine.signal('c', 'activated');
    expect(machine.documents().map((record) => record.fileId)).toEqual(['a', 'b', 'c']);
    machine.forget('c');
    expect(machine.documents().map((record) => record.fileId)).toEqual(['a', 'b']);
    expect(machine.active()).toBe('b');
  });

  it('records the open duration once the render settles', () => {
    let now = 1_000;
    const machine = new DocumentStateMachine(() => now);
    machine.begin('f1', 'plan.dxf');
    now = 1_450;
    expect(machine.renderIdle('f1')?.durationMs).toBe(450);
  });

  it('never leaves a failed document in a ready state', () => {
    const machine = new DocumentStateMachine();
    machine.begin('f1', 'plan.dxf');
    machine.fail('f1', 'broken');
    machine.renderIdle('f1');
    expect(machine.get('f1')?.state).toBe('failed');
    expect(machine.status()).toBe('failed');
  });

  it('reports the worst state as the host status', () => {
    const machine = new DocumentStateMachine();
    expect(machine.status()).toBe('idle');
    machine.begin('a', 'a.dxf');
    expect(machine.status()).toBe('opening');
    machine.signal('a', 'activated');
    machine.beginRender('a');
    expect(machine.status()).toBe('rendering');
    machine.renderIdle('a');
    expect(machine.status()).toBe('ready');
    machine.begin('b', 'b.dxf');
    expect(machine.status()).toBe('opening');
  });
});

// ---------------------------------------------------------------------------
// tiers
// ---------------------------------------------------------------------------

describe('entity tiers (ADR-0002 개정 §5)', () => {
  it('puts the boundaries at 250k and 800k entities', () => {
    expect(tierOf(0)).toBe('A');
    expect(tierOf(250_000)).toBe('A');
    expect(tierOf(250_001)).toBe('B');
    expect(tierOf(800_000)).toBe('B');
    expect(tierOf(800_001)).toBe('C');
  });

  it('estimates from the measured per-format densities', () => {
    // F11: 41.4 MB DXF / 5.3 MB DWG, 200 006 entities — both land in tier A.
    expect(estimateEntityTier({ byteLength: 41_400_000, format: 'dxf' })).toMatchObject({
      tier: 'A',
    });
    expect(estimateEntityTier({ byteLength: 5_300_000, format: 'dwg' })).toMatchObject({
      tier: 'A',
    });
    expect(
      estimateEntityTier({ byteLength: 251_000 * DXF_BYTES_PER_ENTITY, format: 'dxf' }).tier
    ).toBe('B');
    expect(
      estimateEntityTier({ byteLength: 801_000 * DWG_BYTES_PER_ENTITY, format: 'dwg' }).tier
    ).toBe('C');
  });

  it('carries an i18n key, never a Korean string', () => {
    const estimate = estimateEntityTier({ byteLength: 300_000 * DXF_BYTES_PER_ENTITY, format: 'dxf' });
    expect(estimate.warnings[0]).toMatchObject({ code: 'tier-b', i18nKey: 'viewer.warning.tierB' });
    expect(JSON.stringify(estimate.warnings)).not.toMatch(/[가-힣]/);
  });

  it('warns a second time only when the real count changes the tier', () => {
    expect(tierChangeWarnings('A', 10_000)).toEqual([]);
    expect(tierChangeWarnings('A', 300_000)).toHaveLength(1);
    expect(tierChangeWarnings('B', 300_000)).toEqual([]);
    // Smaller than expected is not worth a second message.
    expect(tierChangeWarnings('B', 1_000)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// facade over a stub surface
// ---------------------------------------------------------------------------

interface Stub {
  surface: ViewSurface;
  emitDocument(event: ViewDocumentEvent): void;
  emitSelection(handles: CadHandle[]): void;
  disposed: () => boolean;
  transientCalls: number;
  /** Boxes handed to `zoomTo`, in call order. */
  zoomCalls: { box: ViewBox; margin: number | undefined }[];
  /** How many times a *batch* visibility change was applied. */
  batchCalls: number;
}

/** A layer table the visibility tests can mutate, in file order. */
function layerTable(): CadLayer[] {
  const layer = (name: string, extra: Partial<CadLayer> = {}): CadLayer => ({
    name,
    color: 7,
    linetype: 'Continuous',
    lineweightMm: 0.25,
    isOff: false,
    isFrozen: false,
    isLocked: false,
    isPlottable: true,
    ...extra,
  });
  return [
    layer('0'),
    layer('A-WALL', { color: 3 }),
    // The three layers of `docs/contracts/compare-dxf.md` §2 screen C toggles.
    layer('__CMP_ADDED', { color: 1 }),
    layer('__CMP_REMOVED', { color: 4 }),
    layer('__CMP_LABEL', { color: 8, isOff: true, isPlottable: false }),
    // A true-colour layer, to pin the ACI fallback of `toLayerDto`.
    layer('X-TRUECOLOR', { color: '#12AB34' }),
    layer('X-FROZEN', { isFrozen: true }),
  ];
}

function stubSurface(overrides: Partial<ViewSurface> = {}): Stub {
  const documentListeners = new Set<(event: ViewDocumentEvent) => void>();
  const selectionListeners = new Set<(handles: CadHandle[]) => void>();
  let disposed = false;
  const state = { transientCalls: 0, batchCalls: 0 };
  const zoomCalls: { box: ViewBox; margin: number | undefined }[] = [];
  const table = layerTable();
  const find = (name: string): CadLayer | undefined =>
    table.find((candidate) => candidate.name === name);
  const surface: ViewSurface = {
    workersReady: () => Promise.resolve(true),
    open: () => Promise.resolve(true),
    activate: () => Promise.resolve(true),
    close: () => Promise.resolve(true),
    documentNames: () => [],
    activeDocumentName: () => null,
    documentHandle: () => null,
    entityCount: () => 42,
    layers: () => table.map((layer) => ({ ...layer })),
    setLayerVisible: (name, visible) => {
      const layer = find(name);
      if (!layer) return false;
      layer.isOff = !visible;
      return true;
    },
    setLayersVisible: (entries) => {
      state.batchCalls += 1;
      const applied: string[] = [];
      for (const name of Object.keys(entries).sort()) {
        const layer = find(name);
        if (!layer) continue;
        layer.isOff = entries[name] !== true;
        applied.push(name);
      }
      return applied;
    },
    layouts: () => [],
    activeLayoutHandle: () => null,
    setActiveLayout: () => true,
    waitUntilIdle: () => Promise.resolve(true),
    nextFrame: () => Promise.resolve(true),
    regen: () => undefined,
    pick: () => [],
    search: () => [],
    selectByBox: () => undefined,
    setSelection: () => undefined,
    selection: () => [],
    highlight: () => undefined,
    unhighlight: () => undefined,
    zoomTo: (box, margin) => {
      zoomCalls.push({ box, margin });
    },
    zoomToFit: () => undefined,
    zoomToLayer: () => true,
    screenToWorld: (point) => point,
    worldToScreen: (point) => point,
    addTransient: (entities) => {
      state.transientCalls += 1;
      return Promise.resolve(entities.map((_, index) => `T${String(index)}`));
    },
    setTransientVisible: () => true,
    removeTransient: () => undefined,
    runCommand: () => Promise.resolve(),
    runEdit: (_label, fn) =>
      fn({ erase: () => 0, move: () => 0, rotate: () => 0, copy: () => [] }),
    undo: () => true,
    redo: () => true,
    canUndo: () => true,
    canRedo: () => false,
    setFontChain: () => Promise.resolve(),
    missingFonts: () => [],
    unresolvedXrefs: () => [],
    onDocument: (callback) => {
      documentListeners.add(callback);
      return () => {
        documentListeners.delete(callback);
      };
    },
    onSelection: (callback) => {
      selectionListeners.add(callback);
      return () => {
        selectionListeners.delete(callback);
      };
    },
    onUndoStack: () => () => undefined,
    onProgress: () => () => undefined,
    onOpenFailed: () => () => undefined,
    onMissedData: () => () => undefined,
    onEntityChanged: () => () => undefined,
    dispose: () => {
      disposed = true;
      return Promise.resolve();
    },
    ...overrides,
  };
  return {
    surface,
    emitDocument: (event) => {
      for (const listener of documentListeners) listener(event);
    },
    emitSelection: (handles) => {
      for (const listener of selectionListeners) listener(handles);
    },
    disposed: () => disposed,
    get transientCalls() {
      return state.transientCalls;
    },
    zoomCalls,
    get batchCalls() {
      return state.batchCalls;
    },
  };
}

function hostOf(stub: Stub): CadHost {
  return CadHost.withSurface(stub.surface, {
    container: null as unknown as HTMLElement,
    assetsBaseUrl: 'halocad://app/viewer',
  });
}

describe('CadHost', () => {
  it('reports an open with tier, counts and a duration, and emits documentOpened', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const opened = vi.fn();
    host.on('documentOpened', opened);

    const result = await host.open('file-1', 'plan.dxf', new ArrayBuffer(1024));
    expect(result).toMatchObject({ fileId: 'file-1', entityCount: 42, tier: 'A', renderIdle: true });
    expect(result.durationMs).toBeGreaterThanOrEqual(0);
    expect(opened).toHaveBeenCalledTimes(1);
    expect(host.getStatus()).toBe('ready');
    await host.dispose();
  });

  it('warns about tier B from the byte size before parsing', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const progress = vi.fn();
    host.on('openProgress', progress);
    // 300 000 entities' worth of DXF bytes.
    await host.open('big', 'big.dxf', new ArrayBuffer(300_000 * DXF_BYTES_PER_ENTITY));
    expect(progress).toHaveBeenCalledWith(
      expect.objectContaining({
        warnings: [expect.objectContaining({ code: 'tier-b' })],
      })
    );
    await host.dispose();
  });

  it('flags a render that never settles instead of hanging', async () => {
    const stub = stubSurface({ waitUntilIdle: () => Promise.resolve(false) });
    const host = hostOf(stub);
    const result = await host.open('f', 'f.dxf', new ArrayBuffer(8));
    expect(result.renderIdle).toBe(false);
    expect(result.warnings.map((warning) => warning.code)).toContain('render-timeout');
    await host.dispose();
  });

  it('turns a refused open into openFailed and a failed status', async () => {
    const stub = stubSurface({ open: () => Promise.resolve(false) });
    const host = hostOf(stub);
    const failed = vi.fn();
    host.on('openFailed', failed);
    await expect(host.open('f', 'f.dxf', new ArrayBuffer(8))).rejects.toThrow(/refused/);
    expect(failed).toHaveBeenCalledTimes(1);
    expect(host.getStatus()).toBe('failed');
    await host.dispose();
  });

  it('maps viewer document events onto fileIds', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const activated = vi.fn();
    host.on('documentActivated', activated);
    await host.open('file-9', 'plan.dxf', new ArrayBuffer(8));
    stub.emitDocument({ name: 'file-9.dxf', kind: 'activated' });
    expect(activated).toHaveBeenCalledWith({ fileId: 'file-9' });
    await host.dispose();
  });

  it('forwards the selection as the whole handle set', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const selection = vi.fn();
    host.on('selectionChanged', selection);
    stub.emitSelection(['A1', 'B2']);
    expect(selection).toHaveBeenCalledWith({ handles: ['A1', 'B2'] });
    await host.dispose();
  });

  it('tracks overlays by id and clears them all', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const first = await host.addOverlay({
      entities: [{ kind: 'line', start: { x: 0, y: 0 }, end: { x: 1, y: 1 } }],
    });
    const second = await host.addOverlay({
      id: 'evidence',
      entities: [{ kind: 'rect', box: { min: { x: 0, y: 0 }, max: { x: 10, y: 10 } } }],
    });
    expect(second).toBe('evidence');
    expect(host.overlayIds()).toEqual([first, 'evidence']);
    expect(host.setOverlayVisible('evidence', false)).toBe(true);
    expect(host.setOverlayVisible('missing', false)).toBe(false);
    host.clearOverlays();
    expect(host.overlayIds()).toEqual([]);
    await host.dispose();
  });

  it('refuses every call after dispose', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    await host.dispose();
    expect(stub.disposed()).toBe(true);
    await expect(host.open('f', 'f.dxf', new ArrayBuffer(8))).rejects.toThrow(/disposed/);
    expect(() => host.setActiveLayout('1F')).toThrow(/disposed/);
    // Idempotent.
    await host.dispose();
  });

  it('unsubscribes listeners on dispose so a late viewer event is harmless', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const selection = vi.fn();
    host.on('selectionChanged', selection);
    await host.dispose();
    stub.emitSelection(['A1']);
    expect(selection).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// layer visibility (R1-00a) — the contract screen C (R1-08) uses
// ---------------------------------------------------------------------------

describe('CadHost layer visibility', () => {
  it('reports the table as LayerDto: positive `visible`, ACI colour, frozen apart', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    const byName = new Map(host.layers().map((layer) => [layer.name, layer]));

    expect([...byName.keys()]).toEqual([
      '0',
      'A-WALL',
      '__CMP_ADDED',
      '__CMP_REMOVED',
      '__CMP_LABEL',
      'X-TRUECOLOR',
      'X-FROZEN',
    ]);
    expect(byName.get('__CMP_ADDED')).toMatchObject({ color: 1, visible: true, frozen: false });
    // `__CMP_LABEL` ships off and unplottable (compare-dxf §2).
    expect(byName.get('__CMP_LABEL')).toMatchObject({ visible: false, plottable: false });
    // A true colour keeps its exact value and still reports a usable ACI slot.
    expect(byName.get('X-TRUECOLOR')).toMatchObject({ color: 7, colorRgb: '#12AB34' });
    // Frozen is reported next to `visible`, not folded into it.
    expect(byName.get('X-FROZEN')).toMatchObject({ visible: true, frozen: true });
    await host.dispose();
  });

  it('setLayerVisible(false) shows up in layers() as visible: false', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);

    expect(host.setLayerVisible('__CMP_REMOVED', false)).toBe(true);
    const hidden = host.layers().find((layer) => layer.name === '__CMP_REMOVED');
    expect(hidden?.visible).toBe(false);

    expect(host.setLayerVisible('__CMP_REMOVED', true)).toBe(true);
    expect(host.layers().find((layer) => layer.name === '__CMP_REMOVED')?.visible).toBe(true);
    await host.dispose();
  });

  it('returns false for a layer the drawing does not have', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    expect(host.setLayerVisible('REV-20260904', false)).toBe(false);
    // …and changes nothing else.
    expect(host.layers().every((layer) => layer.visible || layer.name === '__CMP_LABEL')).toBe(true);
    await host.dispose();
  });

  it('setLayersVisible applies a whole view mode in one batch', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);

    // 전 (before): hide what only the after drawing has.
    host.setLayersVisible({ __CMP_ADDED: false, __CMP_REMOVED: true });
    expect(stub.batchCalls).toBe(1);
    const before = new Map(host.layers().map((layer) => [layer.name, layer.visible]));
    expect(before.get('__CMP_ADDED')).toBe(false);
    expect(before.get('__CMP_REMOVED')).toBe(true);

    // 겹쳐 보기 (overlay): both on again, still one batch.
    host.setLayersVisible({ __CMP_ADDED: true, __CMP_REMOVED: true });
    expect(stub.batchCalls).toBe(2);
    const overlay = new Map(host.layers().map((layer) => [layer.name, layer.visible]));
    expect(overlay.get('__CMP_ADDED')).toBe(true);
    expect(overlay.get('__CMP_REMOVED')).toBe(true);
    await host.dispose();
  });

  it('ignores unknown names inside a batch instead of throwing', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    expect(() => {
      host.setLayersVisible({ 'not-a-layer': false, __CMP_ADDED: false });
    }).not.toThrow();
    expect(host.layers().find((layer) => layer.name === '__CMP_ADDED')?.visible).toBe(false);
    await host.dispose();
  });

  it('refuses layer changes after dispose', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);
    await host.dispose();
    expect(() => host.setLayerVisible('__CMP_ADDED', false)).toThrow(/disposed/);
    expect(() => {
      host.setLayersVisible({ __CMP_ADDED: false });
    }).toThrow(/disposed/);
  });

  it('zoomTo accepts both the flat cluster bbox and the {min,max} box', async () => {
    const stub = stubSurface();
    const host = hostOf(stub);

    // What `clusters[].bbox` ([x0, y0, x1, y1]) unpacks to in screen C.
    host.zoomTo({ minX: 10, minY: 20, maxX: 110, maxY: 220 }, 1.2);
    host.zoomTo({ min: { x: 10, y: 20 }, max: { x: 110, y: 220 } });

    expect(stub.zoomCalls).toEqual([
      { box: { min: { x: 10, y: 20 }, max: { x: 110, y: 220 } }, margin: 1.2 },
      { box: { min: { x: 10, y: 20 }, max: { x: 110, y: 220 } }, margin: undefined },
    ]);
    await host.dispose();
  });

  it('whenRenderIdle waits for the scene and then for a painted frame', async () => {
    const order: string[] = [];
    const stub = stubSurface({
      waitUntilIdle: () => {
        order.push('idle');
        return Promise.resolve(true);
      },
      nextFrame: () => {
        order.push('frame');
        return Promise.resolve(true);
      },
    });
    const host = hostOf(stub);
    // `open()` uses both as well; measure only the explicit call.
    order.length = 0;
    expect(await host.whenRenderIdle()).toBe(true);
    expect(order).toEqual(['idle', 'frame']);
    await host.dispose();
  });
});
