/**
 * W1-04 — mlightcad 1.6.3 integration spike.
 *
 * Throwaway fact-finding harness. Every probe answers one numbered question in
 * docs/spikes/mlightcad-api.md and records its outcome into `window.__spike`
 * so Playwright (scripts/screenshots.mjs) can dump it as JSON.
 *
 * Nothing here is meant for reuse; the reusable shape is the CadHost facade
 * proposal in the W1-04 report.
 */
import {
  AcApDocManager,
  AcEdOpenMode,
  acapRunDatabaseEdit,
  eventBus,
} from '@mlightcad/cad-simple-viewer';
import {
  AcDbDatabase,
  AcDbDatabaseConverterManager,
  AcDbFileType,
  AcDbLine,
  AcDbEntity,
  AcDbBlockReference,
  AcDbHatch,
  AcDbPolyline,
  AcDbText,
  AcDbMText,
  AcDbCircle,
  AcDbArc,
  AcDbDimension,
  AcDbViewport,
  AcGeBox2d,
  AcGePoint2d,
  AcGePoint3d,
  AcGeMatrix3d,
} from '@mlightcad/data-model';
import type { AcGeIntersectPrimitive } from '@mlightcad/geometry-engine';
import { AcDbLibreDwgConverter } from '@mlightcad/libredwg-converter';
import { FontManager } from '@mlightcad/mtext-renderer';

// --------------------------------------------------------------------------
// report plumbing
// --------------------------------------------------------------------------
type Verdict = 'confirmed' | 'unavailable' | 'conditional';
interface Fact {
  id: string;
  title: string;
  verdict: Verdict;
  detail: unknown;
}
const facts: Fact[] = [];
const logEl = document.getElementById('log')!;
declare global {
  interface Window {
    __spike: { facts: Fact[]; ready: boolean; errors: string[] };
    __spikeRunAll: () => Promise<void>;
    __spikeOpen: (which: 'dxf' | 'cp949' | 'dwg') => Promise<boolean>;
  }
}
window.__spike = { facts, ready: false, errors: [] };

function line(cls: string, text: string) {
  const d = document.createElement('div');
  d.className = cls;
  d.textContent = text;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}
function record(id: string, title: string, verdict: Verdict, detail: unknown) {
  facts.push({ id, title, verdict, detail });
  const cls = verdict === 'confirmed' ? 'ok' : verdict === 'unavailable' ? 'bad' : 'warn';
  line(cls, `[${id}] ${verdict.toUpperCase()} — ${title}`);
  line('', '   ' + JSON.stringify(detail));
}
async function probe(id: string, title: string, fn: () => Promise<unknown> | unknown) {
  try {
    const detail = await fn();
    const verdict: Verdict =
      detail && typeof detail === 'object' && 'verdict' in (detail as Record<string, unknown>)
        ? ((detail as { verdict: Verdict }).verdict as Verdict)
        : 'confirmed';
    record(id, title, verdict, detail);
  } catch (e) {
    record(id, title, 'unavailable', { error: String((e as Error)?.stack ?? e).slice(0, 600) });
  }
}

// --------------------------------------------------------------------------
// captured global events
// --------------------------------------------------------------------------
const busEvents: Array<{ name: string; payload: unknown; t: number }> = [];
const T0 = performance.now();
for (const name of [
  'fonts-not-found',
  'fonts-not-loaded',
  'font-not-found',
  'failed-to-get-avaiable-fonts',
  'failed-to-open-file',
  'missed-data-changed',
  'undo-stack-changed',
  'session-db-edit-committed',
  'message',
] as const) {
  eventBus.on(name, (payload: unknown) =>
    busEvents.push({ name, payload: JSON.parse(JSON.stringify(payload ?? {})), t: Math.round(performance.now() - T0) })
  );
}

// --------------------------------------------------------------------------
// boot
// --------------------------------------------------------------------------
const BASE = location.origin; // self-hosted: fonts resolve to `${BASE}/fonts/`
const WORKERS = {
  mtextRender: `${BASE}/workers/mtext-renderer-worker.js`,
  dwgParser: `${BASE}/workers/libredwg-parser-worker.js`,
};

AcDbDatabaseConverterManager.instance.register(
  AcDbFileType.DWG,
  new AcDbLibreDwgConverter({ parserWorkerUrl: WORKERS.dwgParser, useWorker: true })
);

const docManager = AcApDocManager.createInstance({
  container: document.getElementById('cad')!,
  autoResize: true,
  baseUrl: BASE,
  webworkerFileUrls: WORKERS,
  checkWorkersOnInit: true,
  builtinOpenFileDialog: false,
})!;

const docEvents: Array<{ name: string; t: number }> = [];
for (const name of [
  'documentToBeOpened',
  'documentCreated',
  'documentActivated',
  'documentToBeActivated',
  'documentToBeDestroyed',
  'documentDestroyed',
  'workersReady',
] as const) {
  docManager.events[name].addEventListener(() =>
    docEvents.push({ name, t: Math.round(performance.now() - T0) })
  );
}

const selectionEvents: Array<{ kind: string; ids: string[] }> = [];
docManager.curView.selectionSet.events.selectionAdded.addEventListener((a) =>
  selectionEvents.push({ kind: 'added', ids: [...a.ids] })
);
docManager.curView.selectionSet.events.selectionRemoved.addEventListener((a) =>
  selectionEvents.push({ kind: 'removed', ids: [...a.ids] })
);
let renderFrames = 0;
docManager.curView.events.renderFrame.addEventListener(() => renderFrames++);

// --------------------------------------------------------------------------
// helpers
// --------------------------------------------------------------------------
const fetchBuf = async (url: string) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.arrayBuffer();
};

function modelSpaceRows(db: AcDbDatabase) {
  const rows: Array<Record<string, unknown>> = [];
  for (const e of db.tables.blockTable.modelSpace.newIterator()) {
    rows.push(entityRow(e));
  }
  return rows;
}

function entityRow(e: AcDbEntity) {
  const row: Record<string, unknown> = {
    handle: e.objectId,
    dxfTypeName: e.dxfTypeName,
    type: e.type,
    layer: e.layer,
    owner: e.ownerId,
  };
  try {
    const b = e.geometricExtents;
    row.bbox = [b.min.x, b.min.y, b.max.x, b.max.y].map((n) => +n.toFixed(3));
  } catch {
    row.bbox = null;
  }
  if (e instanceof AcDbText) row.textString = e.textString;
  if (e instanceof AcDbMText) row.contents = e.contents;
  if (e instanceof AcDbBlockReference) {
    row.blockName = e.blockName;
    row.position = [e.position.x, e.position.y];
    row.rotation = e.rotation;
    row.scaleFactors = [e.scaleFactors.x, e.scaleFactors.y, e.scaleFactors.z];
    try {
      const m = e.blockTransform;
      row.blockTransform = Array.from((m as unknown as { elements: number[] }).elements ?? []);
    } catch {
      row.blockTransform = null;
    }
    const attrs: Array<Record<string, unknown>> = [];
    for (const a of e.attributeIterator()) attrs.push({ tag: a.tag, value: a.textString, handle: a.objectId });
    row.attributes = attrs;
  }
  if (e instanceof AcDbPolyline) {
    row.closed = e.closed;
    row.numberOfVertices = e.numberOfVertices;
    row.area = e.area;
    row.length = curveLength(e);
  }
  if (e instanceof AcDbCircle) row.radius = e.radius;
  if (e instanceof AcDbArc) {
    row.radius = e.radius;
    row.startAngle = e.startAngle;
    row.endAngle = e.endAngle;
  }
  if (e instanceof AcDbLine) {
    row.length = e.startPoint.distanceTo(e.endPoint);
  }
  if (e instanceof AcDbHatch) {
    row.area = e.area;
    row.patternName = e.patternName;
  }
  if (e instanceof AcDbDimension) {
    row.dimBlockId = e.dimBlockId;
    row.measurement = e.measurement;
    row.dimensionStyleName = e.dimensionStyleName;
    row.dimensionText = e.dimensionText;
  }
  return row;
}

/**
 * There is no public `length` getter on AcDbCurve / AcDbPolyline. The only
 * public route to a curve length is `subGetIntersectCurves()`, whose
 * AcGeIntersectPrimitive union carries AcGeLine3d / AcGeCircArc3d /
 * AcGeEllipseArc3d / AcGeSpline3d, each of which does expose `length`.
 */
function curveLength(e: AcDbEntity): number {
  let total = 0;
  const prims = (e as unknown as { subGetIntersectCurves?: () => AcGeIntersectPrimitive[] })
    .subGetIntersectCurves?.();
  for (const prim of prims ?? []) {
    if (prim.kind === 'line') total += prim.line.length;
    else if (prim.kind === 'circArc') total += prim.arc.length;
    else if (prim.kind === 'ellipseArc') total += prim.arc.length;
    else if (prim.kind === 'spline') total += prim.spline.length;
  }
  return +total.toFixed(6);
}

function statsByLayer(db: AcDbDatabase) {
  const out: Record<string, Record<string, number>> = {};
  const bump = (layer: string, key: string, by = 1) => {
    (out[layer] ??= {})[key] = ((out[layer] ??= {})[key] ?? 0) + by;
  };
  for (const e of db.tables.blockTable.modelSpace.newIterator()) {
    bump(e.layer, e.dxfTypeName);
    if (e instanceof AcDbLine) bump(e.layer, '_length', curveLength(e));
    if (e instanceof AcDbArc) bump(e.layer, '_length', curveLength(e));
    if (e instanceof AcDbPolyline) bump(e.layer, '_length', curveLength(e));
    if (e instanceof AcDbHatch) bump(e.layer, '_area', e.area);
  }
  for (const layer of Object.keys(out)) {
    for (const k of Object.keys(out[layer])) out[layer][k] = +out[layer][k].toFixed(6);
  }
  return out;
}

async function openFixture(name: string, url: string) {
  const buf = await fetchBuf(url);
  const bytes = buf.byteLength;
  const t0 = performance.now();
  const ok = await docManager.openDocument(name, buf, { mode: AcEdOpenMode.Write });
  const parseMs = Math.round(performance.now() - t0);
  await docManager.curView.waitUntilIdle(60000);
  return {
    ok,
    bytes,
    parseMs,
    totalMs: Math.round(performance.now() - t0),
    // The DWG worker path transfers the input buffer, leaving it detached.
    inputBufferDetachedAfterOpen: buf.byteLength === 0 && bytes > 0,
  };
}

/**
 * Korean glyph fallback. The shipped default chain (`modern` preset:
 * hztxt → simsun → simplex, symbols amgdt) has no Hangul coverage, so any
 * TEXT/MTEXT whose STYLE has no Korean SHX big font renders as `?`.
 */
async function applyKoreanFallback() {
  const fm = FontManager.instance;
  const available = await fm.getAvailableFonts();
  const hasTtf = available.some((f) => f.file === 'applegothic.ttf');
  const chain = hasTtf
    ? ['whgtxt', 'applegothic', 'hztxt', 'simsun', 'simplex']
    : ['whgtxt', 'hztxt', 'simsun', 'simplex'];
  // main-thread FontManager (used by SHX shape rendering and font mapping)
  fm.setDefaultFonts(chain);
  fm.setFontMapping({ txt: 'whgtxt', romans: 'whgtxt' });
  await fm.loadFontsByNames(chain);
  // MTEXT is laid out in the mtext-renderer web worker, which owns its OWN
  // FontManager instance. Main-thread setDefaultFonts() does not reach it —
  // AcTrMTextRenderer.setDefaultFonts() is the API that syncs the worker pool.
  const { AcTrMTextRenderer } = await import('@mlightcad/three-renderer');
  await AcTrMTextRenderer.getInstance().setDefaultFonts(chain);
  await AcApDocManager.instance.loadDefaultFonts(chain);
  AcApDocManager.instance.regen();
  await AcApDocManager.instance.curView.waitUntilIdle(30000);
  return { chain, hasTtf, workerSyncApi: 'AcTrMTextRenderer.getInstance().setDefaultFonts(chain)' };
}
(window as unknown as { __spikeKoreanFallback: () => Promise<unknown> }).__spikeKoreanFallback =
  applyKoreanFallback;

window.__spikeOpen = async (which) => {
  const map = {
    dxf: ['F-spike-r2018.dxf', '/fixtures/F-spike-r2018.dxf'],
    cp949: ['F-spike-r2000-cp949.dxf', '/fixtures/F-spike-r2000-cp949.dxf'],
    dwg: ['canteen.dwg', '/fixtures/canteen.dwg'],
  } as const;
  const [n, u] = map[which];
  const r = await openFixture(n, u);
  line(r.ok ? 'ok' : 'bad', `open ${n}: ${JSON.stringify(r)}`);
  return r.ok;
};

// --------------------------------------------------------------------------
// the probes
// --------------------------------------------------------------------------
async function runAll() {
  facts.length = 0;
  logEl.textContent = '';
  window.__spike.ready = false;

  await probe('0-versions', 'package versions actually loaded', () => ({
    'cad-simple-viewer': __PKG__['@mlightcad/cad-simple-viewer'],
    'data-model': __PKG__['@mlightcad/data-model'],
    'three-renderer': __PKG__['@mlightcad/three-renderer'],
    'mtext-renderer': __PKG__['@mlightcad/mtext-renderer'],
    'libredwg-converter': __PKG__['@mlightcad/libredwg-converter'],
    'libredwg-web': __PKG__['@mlightcad/libredwg-web'],
    three: __PKG__['three'],
  }));

  // ---- worker wiring -----------------------------------------------------
  await probe('worker-wiring', 'AcApDocManager.createInstance({ webworkerFileUrls }) + areWorkersReady()', async () => ({
    optionKey: 'webworkerFileUrls',
    keys: ['mtextRender', 'dwgParser'],
    urls: WORKERS,
    workersReadyBeforeCheck: docManager.workersReady,
    areWorkersReady: await docManager.areWorkersReady(),
    staticCheck: await AcApDocManager.checkWebworkerReadiness(WORKERS),
    dwgConverterRegistered: !!AcDbDatabaseConverterManager.instance.get(AcDbFileType.DWG),
    registeredFileTypes: [...AcDbDatabaseConverterManager.instance.fileTypes],
  }));

  // ---- fonts (self hosted) ----------------------------------------------
  await probe('fonts', 'self-hosted font repository via baseUrl', async () => {
    const fm = FontManager.instance;
    const available = await fm.getAvailableFonts();
    const before = busEvents.filter((e) => e.name.includes('font')).length;
    const status = await fm.loadFontsByNames(['whgtxt', 'txt', 'simsun', 'amgdt', 'no-such-font']);
    return {
      docManagerBaseUrl: docManager.baseUrl,
      fontManagerBaseUrl: fm.baseUrl,
      manifestUrl: `${fm.baseUrl}fonts.json`,
      availableCount: available.length,
      availableNames: available.map((f) => f.name.join('|')),
      koreanShx: available.filter((f) => /whg/i.test(f.file)).map((f) => ({ file: f.file, encoding: f.encoding })),
      meshFallback: available.filter((f) => f.type === 'mesh').map((f) => f.file),
      loadStatus: status,
      defaultChain: fm.getFontsToLoad(),
      newFontEventsDuringLoad: busEvents.filter((e) => e.name.includes('font')).length - before,
    };
  });

  // ---- 1. open + enumerate ----------------------------------------------
  const opened = await openFixture('F-spike-r2018.dxf', '/fixtures/F-spike-r2018.dxf');

  // ---- Korean glyph coverage (default chain vs. configured fallback) -----
  await probe('fonts-korean', 'Korean glyph coverage with the default font chain', async () => {
    const fm = FontManager.instance;
    const view = docManager.curView;
    const beforeUnsupported = { ...fm.getUnsupportedChar() };
    const beforeMissed = { ...fm.missedFonts };
    const beforeMissedData = JSON.parse(JSON.stringify(view.missedData?.fonts ?? {}));
    const fallback = await applyKoreanFallback();
    const afterUnsupported = { ...fm.getUnsupportedChar() };
    return {
      styleWithKoreanBigFont: 'HANGUL (STYLE 3=txt.shx, 4=whgtxt.shx) — TEXT/ATTRIB render Hangul correctly',
      styleWithoutBigFont: 'Standard (3=txt.shx, 4=empty) — MTEXT Hangul renders as `?` under the shipped default chain',
      defaultChainShipped: ['hztxt', 'simsun', 'simplex'],
      symbolChainShipped: ['amgdt'],
      koreanCoverageInShippedChain: false,
      unsupportedCharsBefore: beforeUnsupported,
      missedFontsBefore: beforeMissed,
      viewMissedDataFonts: beforeMissedData,
      fixApi: 'AcTrMTextRenderer.getInstance().setDefaultFonts(chain)  [worker pool]  +  FontManager.instance.setDefaultFonts(chain) / setFontMapping({...})  [main thread]  +  AcApDocManager.loadDefaultFonts(chain)  +  AcApDocManager.regen()',
      workerCaveat: 'FontManager.setFontMapping() exists only on the main thread; the mtext worker pool has no mapping channel in 1.6.3, so SHX substitution for MTEXT needs useMainThreadDraw:true or an upstream change',
      appliedChain: fallback.chain,
      koreanTtfAvailable: fallback.hasTtf,
      unsupportedCharsAfter: afterUnsupported,
      eventsSeen: busEvents.filter((e) => e.name.includes('font')),
      note: 'the mlightcad font repository ships Korean SHX big fonts (whgtxt/whgdtxt/whtgtxt/whtmtxt, encoding euc-kr) but no Hangul mesh/TTF font',
    };
  });
  const db = docManager.curDocument.database;

  await probe('1-enumerate', 'model space enumeration + fields', () => ({
    open: opened,
    api: 'db.tables.blockTable.modelSpace.newIterator()',
    dwgVersion: db.version,
    fileName: docManager.curDocument.fileName,
    modelSpaceCount: db.tables.blockTable.modelSpace.newIterator().count,
    rows: modelSpaceRows(db),
    paperSpaceRows: (() => {
      const rows: Array<Record<string, unknown>> = [];
      for (const btr of db.tables.blockTable.newIterator()) {
        if (btr.name !== '*Paper_Space') continue;
        for (const e of btr.newIterator()) rows.push(entityRow(e));
      }
      return rows;
    })(),
    blockDefs: (() => {
      const b: Array<Record<string, unknown>> = [];
      for (const btr of db.tables.blockTable.newIterator()) {
        let n = 0;
        for (const _ of btr.newIterator()) n++;
        b.push({ name: btr.name, handle: btr.objectId, entities: n });
      }
      return b;
    })(),
    layers: (() => {
      const l: Array<Record<string, unknown>> = [];
      for (const r of db.tables.layerTable.newIterator())
        l.push({ name: r.name, handle: r.objectId, isOff: r.isOff, isFrozen: r.isFrozen, isLocked: r.isLocked, lineWeight: r.lineWeight, linetype: r.linetype });
      return l;
    })(),
  }));

  // ---- 2. per-layer statistics ------------------------------------------
  await probe('2-stats', 'geometry access needed for statsByLayer()', () => ({
    statsByLayer: statsByLayer(db),
    note: 'no public length getter on AcDbCurve; length summed from subGetIntersectCurves() primitives (AcGeLine3d.length / AcGeCircArc3d.length / AcGeSpline3d.length)',
    hatchAreaApi: 'AcDbHatch.area',
    polylineAreaApi: 'AcDbPolyline.area',
    entityPropertiesSample: (() => {
      const first = [...db.tables.blockTable.modelSpace.newIterator()][1];
      const p = first.properties;
      return { type: p.type, groups: p.groups.map((g) => ({ groupName: g.groupName, properties: g.properties.map((x) => ({ name: x.name, type: x.type, editable: x.editable, value: safe(() => x.accessor.get()) })) })) };
    })(),
  }));

  // ---- 3. pick / search / selectByBox / highlight / zoomTo --------------
  await probe('3-pick', 'pick / search / selectByBox / highlight / zoomTo', () => {
    const view = docManager.curView;
    selectionEvents.length = 0;
    const hitCircle = view.pick(new AcGePoint2d(50, 30), 8, false); // on the circle rim
    const searched = view.search(new AcGeBox2d(new AcGePoint2d(-10, -10), new AcGePoint2d(210, 160)));
    view.selectByBox(new AcGeBox2d(new AcGePoint2d(-5, -5), new AcGePoint2d(210, 160)));
    const selectedIds = [...view.selectionSet.ids];
    view.highlight(['104']);
    view.unhighlight(['104']);
    const bboxBefore = { x: view.center.x, y: view.center.y };
    view.zoomTo(new AcGeBox2d(new AcGePoint2d(0, 0), new AcGePoint2d(100, 100)), 1.1);
    const bboxAfter = { x: view.center.x, y: view.center.y };
    const zoomedLayer = view.zoomToFitLayer('A-TEXT');
    view.zoomToFitDrawing();
    return {
      pickApi: 'AcTrView2d.pick(point, hitRadiusPx, pickOneOnly) → AcEdSpatialQueryResultItemEx[]',
      pickAt50_30: hitCircle.map((h) => h.id),
      searchApi: 'AcTrView2d.search(AcGeBox2d) → AcEdSpatialQueryResultItemEx[]',
      searchCount: searched.length,
      searchIds: searched.map((h) => h.id),
      selectByBoxIds: selectedIds,
      selectionEvents,
      selectionSetApi: 'AcTrView2d.selectionSet (AcEdSelectionSet: add/delete/has/clear/ids/count)',
      highlightApi: 'AcTrView2d.highlight(ids) / unhighlight(ids)',
      zoomToChangedCenter: bboxBefore.x !== bboxAfter.x || bboxBefore.y !== bboxAfter.y,
      zoomToFitLayerReturned: zoomedLayer,
      screenToWorld: (() => { const p = view.screenToWorld({ x: 10, y: 10 }); return [p.x, p.y]; })(),
    };
  });

  // ---- 4. events ---------------------------------------------------------
  await probe('4-events', 'document / selection / render events', () => ({
    docManagerEvents: Object.keys(docManager.events),
    docEventsSeen: docEvents,
    viewEvents: ['mouseMove', 'viewResize', 'viewChanged', 'hover', 'unhover', 'renderFrame'],
    renderFramesSoFar: renderFrames,
    selectionSetEvents: ['selectionAdded', 'selectionRemoved'],
    editorEvents: ['sysVarChanged', 'commandWillStart', 'commandEnded'],
    databaseEvents: Object.keys(db.events),
    globalBusEvents: busEvents.slice(0, 40),
    note: 'no single "render complete" event; use AcTrView2d.waitUntilIdle(timeoutMs) or isProcessingEntities',
    waitUntilIdle: typeof docManager.curView.waitUntilIdle,
  }));

  // ---- 5. transient overlay + markup sidecar -----------------------------
  await probe('5-overlay', 'transient entities + markup/measurement sidecars', async () => {
    const view = docManager.curView;
    const t = new AcDbLine(new AcGePoint3d(0, 160, 0), new AcGePoint3d(200, 160, 0));
    t.layer = 'A-TEXT';
    t.objectId = 'spike-transient-1';
    view.addTransientEntity(t);
    // AcTrView2d.addTransientEntity() is fire-and-forget: it kicks off
    // AcTrEntity.asyncDraw() and only publishes into AcTrScene when that
    // resolves. There is no returned promise, so a caller has to wait.
    await new Promise((r) => setTimeout(r, 500));
    // AcTrView2d.setTransientEntityVisible() returns void; only the scene-level
    // method reports whether the id exists.
    const sceneHiddenOk = view.cadScene.setTransientEntityVisible('spike-transient-1', false);
    const sceneShownOk = view.cadScene.setTransientEntityVisible('spike-transient-1', true);
    const unknownId = view.cadScene.setTransientEntityVisible('no-such-transient', false);
    const inDatabaseScene = view.hasEntity('spike-transient-1');
    const markupCmds = commandNames().filter((c) => /MARKUP|CLOUD|CALLOUT|STAMP|REVCLOUD/.test(c));
    const measureCmds = commandNames().filter((c) => /MEASURE/.test(c));
    return {
      api: 'AcTrView2d.addTransientEntity(entity|entities) / removeTransientEntity(objectId) / setTransientEntityVisible(objectId, visible)',
      transientPublishedToScene: sceneHiddenOk && sceneShownOk,
      unknownIdToggle: unknownId,
      hasEntityForTransient: inDatabaseScene,
      note: 'AcTrView2d.addTransientEntity() is async fire-and-forget (asyncDraw().then(...)) and returns void; AcTrView2d.setTransientEntityVisible() also returns void — only AcTrScene.setTransientEntityVisible() returns boolean. AcTrView2d.hasEntity() never sees transients.',
      previewApi: 'createEntityPreview(ids) / updateEntityPreview(handle, AcGeMatrix3d) / removeEntityPreview(handle)',
      markupSidecar: {
        format: 'AcApMarkupSidecarFile { version: 1, drawingName?, markups: AcApMarkupRecord[] }',
        record: 'AcApMarkupMeta { id,type,layoutId?,style{color,lineWeight?,fontSize?},text?,comment,status,author,createdAt,updatedAt } & { geometry }',
        types: ['text', 'line', 'arrow', 'cloud', 'rect', 'circle', 'highlight', 'callout', 'stamp', 'symbol'],
        status: ['open', 'question', 'answered', 'closed'],
        helpers: ['parseMarkupSidecar', 'stringifyMarkupSidecar', 'markupSidecarFileName'],
        commands: markupCmds,
      },
      measurement: {
        helpers: ['parseMeasurementSidecar', 'stringifyMeasurementSidecar', 'measurementSidecarFileName'],
        commands: measureCmds,
      },
    };
  });

  // ---- 6. edit transaction + undo ----------------------------------------
  await probe('6-edit-undo', 'acapRunDatabaseEdit + undo/redo', () => {
    const tm = db.transactionManager;
    const before = countModelSpace(db);
    const beforeCanUndo = tm.canUndo();
    acapRunDatabaseEdit(db, 'spike: append line', () => {
      const l = new AcDbLine(new AcGePoint3d(0, 130, 0), new AcGePoint3d(200, 130, 0));
      l.layer = 'A-WALL';
      db.tables.blockTable.modelSpace.appendEntity(l);
    });
    const afterAppend = countModelSpace(db);
    const undone = tm.undo();
    const afterUndo = countModelSpace(db);
    const redone = tm.redo();
    const afterRedo = countModelSpace(db);
    tm.undo(); // leave the fixture as loaded

    // entity service edit (move / rotate / clone / erase) under one undo mark
    const svc = docManager.curDocument.entityService;
    const circle = svc.getEntitiesByIds(['102']);
    const moved = svc.runEdit('spike: move circle', () => svc.translateEntities(circle, { x: 5, y: 5, z: 0 }));
    const rotated = svc.runEdit('spike: rotate circle', () => svc.rotateEntities(circle, { x: 0, y: 0, z: 0 }, Math.PI / 8));
    const cloned = svc.runEdit('spike: clone circle', () =>
      svc.cloneAndTransform(circle, AcGeMatrix3d.makeTranslation(0, -60, 0), { append: true }).length
    );
    const erased = svc.runEdit('spike: erase clone', () => svc.eraseEntities([...db.tables.blockTable.modelSpace.newIterator()].slice(-1).map((e) => e.objectId)));
    tm.undo(); tm.undo(); tm.undo(); tm.undo();

    return {
      appEditApi: 'acapRunDatabaseEdit(db, label, fn) — wraps AcDbDatabase.runDatabaseEdit and emits `undo-stack-changed`',
      dbEditApi: 'AcDbDatabase.runDatabaseEdit(label, fn)',
      txApi: 'AcDbDatabase.transactionManager: startTransaction/commitTransaction/abortTransaction/startUndoMark(label)/endUndoMark/cancelUndoMark/undo/redo/canUndo/canRedo/clearUndoStack',
      counts: { before, afterAppend, afterUndo, afterRedo },
      undoReturned: undone,
      redoReturned: redone,
      canUndoBefore: beforeCanUndo,
      canUndoNow: tm.canUndo(),
      entityService: 'AcApDocument.entityService (AcApEntityService): transformEntities/translateEntities/rotateEntities/cloneAndTransform/eraseEntities/moveEntitiesToCurrentLayer/runEdit',
      entityServiceResults: { moved, rotated, cloned, erased },
      undoCommands: ['UNDO (alias U)', 'REDO'],
    };
  });

  // ---- 7. dxfOut round-trip ---------------------------------------------
  await probe('7-dxfout', 'AcDbDatabase.dxfOut() round-trip', async () => {
    const beforeRows = modelSpaceRows(db);
    const t0 = performance.now();
    const out = db.dxfOut('roundtrip.dxf', 6, 'AC1032');
    const ms = Math.round(performance.now() - t0);
    const text = typeof out === 'string' ? out : new TextDecoder().decode(out);
    const db2 = new AcDbDatabase();
    await db2.read(new TextEncoder().encode(text).buffer as ArrayBuffer, { readOnly: true }, AcDbFileType.DXF);
    const afterRows = modelSpaceRows(db2);

    const binary = db.dxfOut('roundtrip.dxf', 6, 'AC1032', { format: 'binary' });
    const r2000 = db.dxfOut('r2000.dxf', 6, 'AC1015');
    const r2000Text = typeof r2000 === 'string' ? r2000 : '';

    const byType = (rows: Array<Record<string, unknown>>) => {
      const m: Record<string, number> = {};
      for (const r of rows) m[String(r.dxfTypeName)] = (m[String(r.dxfTypeName)] ?? 0) + 1;
      return m;
    };
    const handles = (rows: Array<Record<string, unknown>>) => rows.map((r) => String(r.handle)).sort();
    const beforeH = handles(beforeRows);
    const afterH = handles(afterRows);

    (window as unknown as { __roundTripDxf: string }).__roundTripDxf = text;

    return {
      signature: "dxfOut(_fileName?, precision?, version?, optionsOrThumbnail?: boolean | { saveThumbnailImage?, format?: 'ascii'|'binary' }) : string | Uint8Array",
      asciiBytes: text.length,
      binaryIsUint8Array: binary instanceof Uint8Array,
      binaryBytes: binary instanceof Uint8Array ? binary.length : null,
      exportMs: ms,
      writtenAcadver: /\$ACADVER\r?\n\s*1\r?\n(\S+)/.exec(text)?.[1],
      writtenAcadverR2000: /\$ACADVER\r?\n\s*1\r?\n(\S+)/.exec(r2000Text)?.[1],
      sectionsWritten: [...text.matchAll(/^\s*2\r?\n(HEADER|CLASSES|TABLES|BLOCKS|ENTITIES|OBJECTS|THUMBNAILIMAGE)\r?$/gm)].map((m) => m[1]),
      before: { count: beforeRows.length, byType: byType(beforeRows) },
      after: { count: afterRows.length, byType: byType(afterRows) },
      handlesPreserved: beforeH.length === afterH.length && beforeH.every((h, i) => h === afterH[i]),
      handlesBefore: beforeH,
      handlesAfter: afterH,
      lostHandles: beforeH.filter((h) => !afterH.includes(h)),
      newHandles: afterH.filter((h) => !beforeH.includes(h)),
      layersBefore: [...db.tables.layerTable.newIterator()].map((l) => `${l.name}#${l.objectId}`),
      layersAfter: [...db2.tables.layerTable.newIterator()].map((l) => `${l.name}#${l.objectId}`),
      blocksBefore: [...db.tables.blockTable.newIterator()].map((b) => `${b.name}#${b.objectId}`),
      blocksAfter: [...db2.tables.blockTable.newIterator()].map((b) => `${b.name}#${b.objectId}`),
      koreanTextRoundTrip: afterRows.filter((r) => r.textString || r.contents).map((r) => r.textString ?? r.contents),
      attributesAfter: afterRows.find((r) => r.dxfTypeName === 'INSERT')?.attributes,
      layoutsAfter: layoutNames(db2),
      viewerCommand: 'CDXF (AcApConvertToDxfCmd) exports the current document through the same path',
    };
  });

  // ---- 8. layouts + viewport drill-down ----------------------------------
  await probe('8-layouts', 'paper space layouts and viewport drill-down', () => {
    const view = docManager.curView;
    const names = layoutNames(db);
    const layoutDict = db.objects.layout;
    const paperBtr = [...db.tables.blockTable.newIterator()].find((b) => b.name === '*Paper_Space');
    const before = view.activeLayoutBtrId;
    let switched: string | null = null;
    if (paperBtr) {
      docManager.setActiveLayout(view, db);
      view.activeLayoutBtrId = paperBtr.objectId;
      switched = view.activeLayoutBtrId;
    }
    const viewports = paperBtr
      ? [...paperBtr.newIterator()].filter((e) => e instanceof AcDbViewport).map((e) => {
          const v = e as AcDbViewport;
          return { handle: v.objectId, number: v.number, width: v.width, height: v.height, centerPoint: [v.centerPoint.x, v.centerPoint.y], viewCenter: [v.viewCenter.x, v.viewCenter.y] };
        })
      : [];
    view.activeLayoutBtrId = before;
    return {
      layoutNames: names,
      layoutDictionary: `AcDbDatabase.objects.layout (AcDbLayoutDictionary), numEntries=${layoutDict.numEntries}`,
      layoutRecords: [...layoutDict.newIterator()].map((l) => ({ name: l.layoutName, tabOrder: l.tabOrder, btrId: l.blockTableRecordId, handle: l.objectId, viewportArray: l.viewportArray })),
      switchApi: 'AcTrView2d.activeLayoutBtrId = <block table record id>  +  AcApDocManager.setActiveLayout(view, db)',
      layoutViewManagerApi: 'AcTrLayoutViewManager (has/getAt/add/activeLayoutView) via AcTrView2d.activeLayoutView',
      modelSpaceBtrId: view.modelSpaceBtrId,
      before,
      switched,
      viewports,
      drillDown: 'AcTrView2d.pick() drills through AcDbViewport rectangles in paper space (pickThroughViewports); near the border the viewport entity itself is picked',
    };
  });

  // ---- 9. XREF -----------------------------------------------------------
  await probe('9-xref', 'XREF resolution and manual attach', async () => {
    const { AcApXrefManager } = await import('@mlightcad/cad-simple-viewer');
    const mgr = AcApXrefManager.instance;
    const missed = docManager.curView.missedData;
    return {
      autoResolution: 'none — the viewer never fetches xref targets by itself',
      evidence: 'AcTrView2d.missedData.xrefs collects { name, pathName, isOverlay } for unresolved external references',
      missedXrefs: missed?.xrefs ?? [],
      manualApi: 'AcApXrefManager.instance.attachOverlay({ blockName, fileName, content|sourceDb, sourcePath, transform?, insertId? }) → AcApXrefSession',
      sessionShape: 'AcApXrefSession { id, blockName, insertId?, overlayId, sourcePath, visible }',
      otherApi: ['setVisible', 'setVisibleByBlockName', 'unload', 'unloadByBlockName', 'clearAll', 'getSessionByBlockName', 'AcApXrefManager.createHostXrefInsert(db, blockName, pathName, transform, origin?)'],
      command: 'XATTACH (alias XA) — AcApXAttachCmd',
      overlayApi: 'AcApDocManager.loadOverlay(fileName, content, options) / registerOverlayDatabase(db) / setOverlayVisible / removeOverlay / clearOverlays / getOverlayIds',
      overlayLimitation: 'AcApDocManager.loadOverlay doc comment: INSERT expansion, viewports and dimensions are skipped in overlay geometry',
      sessionsNow: mgr.sessions.length,
    };
  });

  // ---- 10. MDI -----------------------------------------------------------
  await probe('10-mdi', 'multi document interface', async () => {
    const buf = await fetchBuf('/fixtures/F-spike-r2000-cp949.dxf');
    const okSecond = await docManager.openDocument('F-spike-r2000-cp949.dxf', buf, { mode: AcEdOpenMode.Write });
    await docManager.curView.waitUntilIdle(30000);
    const docs = docManager.documents.map((d) => ({ fileName: d.fileName, title: d.docTitle, mode: d.openMode }));
    const first = docManager.document(0)!;
    const activated = await docManager.activateDocument(first);
    const koreanFromCp949 = [...docManager.documents]
      .map((d) => ({
        file: d.fileName,
        text: [...d.database.tables.blockTable.modelSpace.newIterator()]
          .filter((e) => e instanceof AcDbText || e instanceof AcDbMText)
          .map((e) => (e instanceof AcDbText ? e.textString : (e as AcDbMText).contents)),
        layers: [...d.database.tables.layerTable.newIterator()].map((l) => l.name),
      }));
    return {
      api: 'AcApDocManager: documents / documentCount / document(i) / activeSessionId / activateDocument(doc) / closeDocument(doc) / sessionFor(doc)',
      splitView: 'ensureSplitView(container) creates a second AcTrView2d; openDocument(..., view) targets it',
      documentCount: docManager.documentCount,
      documents: docs,
      okSecond,
      activatedFirst: activated,
      cp949Decoding: koreanFromCp949,
      caveat: 'one shared AcTrView2d per canvas; switching parks/restores the scene via captureSessionState/restoreSessionState',
    };
  });

  // ---- 11. headless ------------------------------------------------------
  await probe('11-headless', 'headless / Node usage', () => ({
    cliPackagePublished: (window as unknown as { __cliProbe?: unknown }).__cliProbe ?? 'see scripts/probe-node.cjs result in docs',
    note: 'measured out-of-band; see docs/spikes/mlightcad-api.md fact 11',
  }));

  // ---- 12. DWG + memory --------------------------------------------------
  await probe('12-dwg', 'DWG load through libredwg worker + memory', async () => {
    const mem0 = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null;
    const r = await openFixture('canteen.dwg', '/fixtures/canteen.dwg');
    const mem1 = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory?.usedJSHeapSize ?? null;
    const dwgDb = docManager.curDocument.database;
    const byType: Record<string, number> = {};
    let n = 0;
    for (const e of dwgDb.tables.blockTable.modelSpace.newIterator()) {
      byType[e.dxfTypeName] = (byType[e.dxfTypeName] ?? 0) + 1;
      n++;
    }
    let dxfOutMs: number | null = null;
    let dxfOutBytes: number | null = null;
    let dxfOutReopenCount: number | null = null;
    try {
      const t0 = performance.now();
      const outText = dwgDb.dxfOut('canteen.dxf', 6, 'AC1032') as string;
      dxfOutMs = Math.round(performance.now() - t0);
      dxfOutBytes = outText.length;
      const db3 = new AcDbDatabase();
      await db3.read(new TextEncoder().encode(outText).buffer as ArrayBuffer, { readOnly: true }, AcDbFileType.DXF);
      dxfOutReopenCount = db3.tables.blockTable.modelSpace.newIterator().count;
    } catch (e) {
      dxfOutMs = -1;
      dxfOutBytes = -1;
      (window.__spike.errors ??= []).push('dwg dxfOut: ' + String(e).slice(0, 200));
    }
    return {
      registration: 'AcDbDatabaseConverterManager.instance.register(AcDbFileType.DWG, new AcDbLibreDwgConverter({ parserWorkerUrl, useWorker: true }))',
      wasm: 'libredwg-web.wasm resolved from `import.meta.url` of libredwg-parser-worker.js — must be a sibling file',
      openResult: r,
      modelSpaceCount: n,
      byType,
      layerCount: [...dwgDb.tables.layerTable.newIterator()].length,
      dwgVersion: dwgDb.version,
      heapBeforeBytes: mem0,
      heapAfterBytes: mem1,
      heapDeltaMB: mem0 && mem1 ? +((mem1 - mem0) / 1048576).toFixed(1) : null,
      dxfOutMs,
      dxfOutBytes,
      dxfOutReopenCount,
    };
  });

  // ---- command inventory (for the capability matrix) ---------------------
  await probe('cmd-inventory', 'registered commands (AcEdCommandStack.iterator())', () => {
    const items: Array<{ group: string; global: string; local: string; mode: number; aliases: string[] }> = [];
    for (const it of docManager.commandManager.iterator()) {
      items.push({
        group: it.commandGroup,
        global: it.command.globalName,
        local: it.command.localName,
        mode: it.command.mode,
        aliases: docManager.commandManager.getCommandAliases(it.command, it.commandGroup),
      });
    }
    items.sort((a, b) => a.global.localeCompare(b.global));
    return { count: items.length, items };
  });

  window.__spike.ready = true;
  line('ok', `--- all probes done (${facts.length}) ---`);
}

function commandNames(): string[] {
  const out: string[] = [];
  for (const it of AcApDocManager.instance.commandManager.iterator()) out.push(it.command.globalName);
  return out;
}
function countModelSpace(db: AcDbDatabase) {
  let n = 0;
  for (const _ of db.tables.blockTable.modelSpace.newIterator()) n++;
  return n;
}
function layoutNames(db: AcDbDatabase): string[] {
  const names: string[] = [];
  try {
    for (const l of db.objects.layout.newIterator()) names.push(l.layoutName);
  } catch {
    /* fall through */
  }
  return names;
}
function safe<T>(fn: () => T): T | string {
  try {
    return fn();
  } catch (e) {
    return 'ERR: ' + String(e).slice(0, 120);
  }
}

declare const __PKG__: Record<string, string>;

window.__spikeRunAll = runAll;
document.getElementById('b-all')!.addEventListener('click', () => void runAll());
document.getElementById('b-dxf')!.addEventListener('click', () => void window.__spikeOpen('dxf'));
document.getElementById('b-cp949')!.addEventListener('click', () => void window.__spikeOpen('cp949'));
document.getElementById('b-dwg')!.addEventListener('click', () => void window.__spikeOpen('dwg'));
document.getElementById('b-json')!.addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(window.__spike, null, 2)], { type: 'application/json' });
  window.open(URL.createObjectURL(blob), '_blank');
});

if (new URLSearchParams(location.search).get('auto') === '1') void runAll();
