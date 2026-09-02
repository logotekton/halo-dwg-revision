# mlightcad 1.6.3 API 참조 (W1-04 스파이크 결과)

작성: 2026-09-02 · 태스크 W1-04 · 실험 코드 `spikes/mlightcad/`
후속 입력: **W3-02**(CadHost 파사드), **W3-05**(폰트·인코딩), **W3-06**(XREF), **W4-03**(편집 명령 보충), **W2-02**(stats/NDJ), **W2-06**(대용량 실측)

## 0. 이 문서의 규칙

- 모든 식별자는 `spikes/mlightcad/node_modules/@mlightcad/*/lib/**/*.d.ts`에서 그대로 옮겼다.
  **브리프는 `dist/*.d.ts`를 지목했지만 실제 타입 선언은 `lib/`에 있다**(`package.json`의 `exports.types = "./lib/index.d.ts"`). 이 문서의 경로는 모두 `lib/` 기준이다.
- 런타임으로 확인한 값은 `spikes/mlightcad/results/browser-facts.json`(브라우저)과 `results/probe-node.json`(Node)에 원본이 있다. 재생성: `npm run dev` 후 `npm run shots`, `npm run probe:node`.
- 판정은 **확인됨 / 조건부 / 불가** 셋 중 하나.

측정 환경: macOS 15 (darwin 25.5.0, arm64), Node v24.20.0, Chromium 151 headless (SwiftShader), Vite 7.3.6.
설치 버전(런타임에서 읽음): `cad-simple-viewer 1.6.3`, `data-model 1.14.3`, `three-renderer 1.6.3`, `mtext-renderer 0.12.4`, `libredwg-converter 3.14.3`, `libredwg-web 0.7.10`, `three 0.172.0`.

## 0.1 스크린샷

| 파일 | 내용 |
|---|---|
| `docs/spikes/img/fixture-korean-default-fonts.png` | 픽스처 DXF, **기본 폰트 체인**. TEXT/ATTRIB(빅폰트 `whgtxt.shx`)는 한글이 나오지만 MTEXT(스타일 `Standard`)는 `?`로 나온다 |
| `docs/spikes/img/fixture-korean-mtext.png` | 같은 픽스처, **한글 폴백 체인 적용 후**. MTEXT `\P` 줄바꿈과 `{\C1; …}` 색상까지 정확 |
| `docs/spikes/img/sample-dwg-canteen.png` | `canteen.dwg`(AC1014, 25 122 엔티티)를 libredwg 워커로 열어 렌더한 결과 |

## 0.2 픽스처

손으로 작성한 DXF(그룹 코드 단위, `spikes/mlightcad/scripts/make-fixtures.mjs`).

| 파일 | 버전 | 인코딩 | 바이트 | sha256 |
|---|---|---|---|---|
| `F-spike-r2018.dxf` | AC1032 | UTF-8 | 10736 | `1faa34b5908d54bb44cb681807443cda12f6b459a2b7fd56703293b94d8557a2` |
| `F-spike-r2000-cp949.dxf` | AC1015 | CP949 | 10679 | `0024f06b29f5508256732ef2f38be9f9648cb2ca97cba7ebe77720e9acfed88f` |

샘플 DWG(공개, mlightcad `cad-data` 저장소):

| URL | 바이트 | sha256 |
|---|---|---|
| `https://cdn.jsdelivr.net/gh/mlightcad/cad-data/data/canteen.dwg` | 2 618 816 | `818f54cd3b413ce3ab00a6aa849bc29cd8cc8581a39fc31a723691f40141fdbc` |

폰트 자체 호스팅용 다운로드 목록과 sha256은 `spikes/mlightcad/fixtures/assets.lock.json`.

---

## A. 부트스트랩과 워커 배선 — 확인됨

```ts
import { AcApDocManager } from '@mlightcad/cad-simple-viewer'
import { AcDbDatabaseConverterManager, AcDbFileType } from '@mlightcad/data-model'
import { AcDbLibreDwgConverter } from '@mlightcad/libredwg-converter'

// GPL 경계: 이 register 호출만 packages/dwg-io-gpl 쪽에 둔다.
AcDbDatabaseConverterManager.instance.register(
  AcDbFileType.DWG,                                   // 'dwg'
  new AcDbLibreDwgConverter({
    parserWorkerUrl: `${base}/workers/libredwg-parser-worker.js`,
    useWorker: true
  })
)

const docManager = AcApDocManager.createInstance({
  container: hostElement,
  autoResize: true,
  baseUrl: base,                                      // 폰트·템플릿 루트
  webworkerFileUrls: {                                // AcApWebworkerFiles
    mtextRender: `${base}/workers/mtext-renderer-worker.js`,
    dwgParser:   `${base}/workers/libredwg-parser-worker.js`
  },
  checkWorkersOnInit: true,
  builtinOpenFileDialog: false                        // 우리 UI가 파일 선택을 담당
})!
await docManager.areWorkersReady()                    // → true (실측)
```

- 옵션 타입: `AcApDocManagerOptions` (`lib/app/AcApDocManager.d.ts`). 브리프가 예상한 `webworkerFileUrls` 키가 그대로 존재한다.
- 워커 파일명 상수: `lib/app/AcApWorkerAssets.d.ts` — `MTEXT_RENDERER_WORKER_FILE = "mtext-renderer-worker.js"`, `LIBREDWG_PARSER_WORKER_FILE = "libredwg-parser-worker.js"`, `LIBREDWG_PARSER_WASM_FILE = "libredwg-web.wasm"`.
- **wasm은 워커 스크립트의 형제 파일이어야 한다.** `dist/libredwg-parser-worker.js`가 `new URL("libredwg-web.wasm", import.meta.url)`로 해석한다(번들 소스 확인). `AcApWorkerAssets.d.ts` 주석도 "Must be deployed next to the worker (wasm is not inlined)"라고 명시.
- 사전 점검 정적 메서드: `AcApDocManager.checkWebworkerReadiness(webworkerFileUrls): Promise<boolean>` — 인스턴스 없이 HEAD 요청으로 확인. 실측 `true`.
- `AcApDocManager.instance.workersReady`는 점검 전 `null`, 이후 boolean. 이벤트 `events.workersReady`.
- **cad-simple-viewer는 DWG 변환기를 스스로 등록하지 않는다**(`AcApWebworkerFiles.dwgParser` JSDoc: "The viewer does **not** register a DWG converter by default (LibreDWG is GPL)"). GPL 격리는 상류가 의도한 설계다.

### 기본 원격 자원 (반드시 재정의)

`dist/cad-simple-viewer.js` 상수: 기본 `baseUrl = "https://cdn.jsdelivr.net/gh/mlightcad/cad-data"`, 템플릿 `"templates/acadiso.dxf"`.
`AcApDocManager`의 `resolveFontsBaseUrl()`은 `` `${baseUrl}/fonts/` `` 를 만들고 `DefaultFontLoader`가 그 아래 `fonts.json`을 가져온다.
**CLAUDE.md 9(런타임 외부 네트워크는 DMS 서버만)** 때문에 `baseUrl`은 반드시 로컬(Electron `dmcad://`)로 바꿔야 한다. 스파이크는 `baseUrl = location.origin`으로 자체 호스팅했고 정상 동작을 확인했다.

### Electron(`dmcad://` 커스텀 스킴)에서 필요한 조건 — 예측

실제 Electron 통합은 W1-01/W3-02 소관이라 여기서는 수행하지 않았다. 위 실측에서 도출되는 요구 사항:

1. **스킴 등록.** `protocol.registerSchemesAsPrivileged([{ scheme: 'dmcad', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }])`가 `app.whenReady()` 전에 필요하다. `standard: true`가 없으면 워커 안의 `new URL('libredwg-web.wasm', import.meta.url)` 상대 해석이 깨진다.
2. **MIME.** 핸들러가 `.js` → `text/javascript`, `.wasm` → `application/wasm`을 반환해야 한다. `application/wasm`이 아니면 `WebAssembly.instantiateStreaming`이 실패하고 폴백 경로로 떨어진다(9.9 MB를 두 번 읽게 된다).
3. **CSP.** `worker-src 'self' blob:`, `script-src 'self'`, `connect-src 'self'`(wasm/폰트 fetch), `img-src 'self' data: blob:`. 워커를 `blob:`으로 감싸면 상대 wasm 경로를 잃으므로 **파일 URL로 직접 로드**해야 한다.
4. **경로 배치.** `dmcad://app/workers/` 아래에 `libredwg-parser-worker.js`와 `libredwg-web.wasm`을 같은 디렉터리로 둔다. electron-vite에서는 이 세 파일을 `publicDir`(또는 빌드 후 복사 스텝)로 옮긴다 — 스파이크의 `scripts/copy-worker-assets.mjs`가 그 최소 구현이다.
5. **폰트.** `baseUrl = 'dmcad://app'` → `dmcad://app/fonts/fonts.json` + 각 SHX/woff. 폰트 파일은 `asar` 밖(`extraResources`)에 두는 편이 스트리밍에 유리하다.
6. **`checkWorkersOnInit: true`** 는 HEAD 요청을 쓴다. 커스텀 스킴 핸들러가 HEAD를 처리하지 않으면 `workersReady`가 false로 남는다 → 핸들러에서 HEAD를 GET과 동일하게 처리하거나 이 옵션을 끄고 `areWorkersReady()`를 쓰지 않는다.
7. **`crossOriginIsolated`는 필요 없다.** libredwg-web wasm은 SharedArrayBuffer/스레드를 쓰지 않는다(스파이크에서 COOP/COEP 없이 정상 동작).

---

## B. 폰트: 자체 호스팅과 한글 — 조건부(설정하면 확인됨)

### B.1 자체 호스팅 배선 — 확인됨

- `AcApDocManagerOptions.baseUrl` → `AcApFontLoader.baseUrl` / `FontManager.instance.baseUrl` = `` `${baseUrl}/fonts/` ``.
- 매니페스트: `` `${fontsBaseUrl}fonts.json` `` (`DefaultFontLoader.getAvailableFonts()`), 항목 타입은 `FontInfo { name: string[]; file: string; type: 'mesh'|'shx'; url: string; encoding?: string; source?: 'remote'|'cache' }` (`mtext-renderer/lib/font/fontLoader.d.ts`).
- 실측: `fontManagerBaseUrl = "http://localhost:5178/fonts/"`, 9개 폰트 인식, `loadFontsByNames(['whgtxt','txt','simsun','amgdt'])` 모두 `status: 'Success'`.

### B.2 한글 SHX 빅폰트 — 확인됨

mlightcad 폰트 저장소(`cad-data/fonts/fonts.json`, 총 97개)에 한글 SHX 빅폰트가 **있다**:
`whgtxt.shx`, `whgdtxt.shx`, `whtgtxt.shx`, `whtmtxt.shx` — 모두 `encoding: "euc-kr"`.
픽스처의 텍스트 스타일 `HANGUL`(DXF 그룹 3=`txt.shx`, 4=`whgtxt.shx`)을 쓰는 **TEXT와 ATTRIB는 기본 상태에서 한글이 정상 렌더**된다(`docs/spikes/img/fixture-korean-default-fonts.png`).

**한글 mesh(TTF/WOFF) 폰트는 저장소에 없다.** 매니페스트의 mesh 폰트는 `arial / tahoma / verdana / simsun / simhei / simkai / simfang / msyh / SJQY / AIGDT / gbgdt` 뿐이며 전부 라틴 또는 중국어다.

### B.3 빅폰트가 없는 스타일의 MTEXT는 기본값에서 `?`로 렌더된다 — 확인됨(수정 방법 확인됨)

- 기본 폴백 체인은 프리셋 `modern`: 텍스트 `hztxt → simsun → simplex`, 심볼 `amgdt` (`AcApDocManager` 생성자에서 `FontManager.instance.setDefaultFonts('modern')`). **한글 커버리지가 없다.**
- 픽스처 MTEXT(핸들 `105`, 스타일 `Standard`, 빅폰트 없음)는 `?? 1? ???` 로 렌더된다 → `docs/spikes/img/fixture-korean-default-fonts.png`.
- 이때 `fonts-not-found` 이벤트가 뜨는 경우는 **폰트 파일 자체가 저장소에 없을 때**뿐이다(실측: `{ fonts: ['simplex'] }`). *글리프* 누락은 이벤트로 오지 않는다.
- **수정 방법(실측으로 검증):**

```ts
import { FontManager } from '@mlightcad/mtext-renderer'
import { AcTrMTextRenderer } from '@mlightcad/three-renderer'

const chain = ['whgtxt', '<한글 mesh 폰트>', 'hztxt', 'simsun', 'simplex']

FontManager.instance.setDefaultFonts(chain)          // 메인 스레드
FontManager.instance.setFontMapping({ txt: 'whgtxt' })
await FontManager.instance.loadFontsByNames(chain)

await AcTrMTextRenderer.getInstance().setDefaultFonts(chain)  // ★ 워커 풀 동기화
await AcApDocManager.instance.loadDefaultFonts(chain)
AcApDocManager.instance.regen()
await AcApDocManager.instance.curView.waitUntilIdle(30000)
```

적용 후 MTEXT가 `지하 1층 평면도 / 축척 1:100 / 검토자 홍길동`으로 정확히 렌더되고 `\P` 줄바꿈과 `{\C1; …}` 색상 코드도 반영된다 → `docs/spikes/img/fixture-korean-mtext.png`.

**함정(W3-05가 반드시 알아야 함):**
1. **MTEXT 레이아웃은 mtext-renderer 웹워커에서 일어나고, 워커는 자기 `FontManager` 인스턴스를 갖는다.** 메인 스레드에서 `FontManager.instance.setDefaultFonts()`만 부르면 MTEXT는 바뀌지 않는다. 워커에 전파하는 유일한 공개 API가 `AcTrMTextRenderer.getInstance().setDefaultFonts(fonts)`(`three-renderer/lib/renderer/AcTrMTextRenderer.d.ts`)다. 하부는 `UnifiedRenderer.setDefaultFonts()`(`mtext-renderer/lib/worker/unifiedRenderer.d.ts`).
2. **`setFontMapping()`에는 워커 전파 채널이 없다.** `UnifiedRenderer`/`AcTrMTextRenderer` 어느 쪽에도 mapping API가 없다. 따라서 "누락 SHX → 대체 폰트" 매핑 UI는 MTEXT에 대해서는 `AcApDocManagerOptions.useMainThreadDraw: true`로 메인 스레드 렌더를 강제하거나, 상류 PR이 필요하다.
3. 같은 이유로 `FontManager.instance.getUnsupportedChar()` / `.missedFonts` / `AcTrView2d.missedData.fonts`는 메인 스레드 결과만 담는다(실측 모두 `{}` — 실제로는 MTEXT 글리프가 빠져 있었다). **누락 폰트 패널의 데이터 소스를 이것만으로 잡으면 안 된다.**
4. 폰트 캐시: `FontManager.instance.cacheFont(data, fileName?, aliases?, encoding?)` + IndexedDB(`idb`). 뷰어 명령 `CACHEFONT`와 이벤트 `cache-font` / `font-file-selected`가 사용자 SHX 업로드 경로다.

### B.4 CP949(ANSI_949) 디코딩 — 확인됨

`F-spike-r2000-cp949.dxf`(AC1015, `$DWGCODEPAGE = ANSI_949`, 파일 전체가 CP949 바이트)를 **원본 ArrayBuffer 그대로** 넘겼을 때, 브라우저·Node 양쪽에서 레이어명 `치수`와 TEXT/MTEXT 한글이 정확히 복원됐다. 관련 export: `acdbDwgCodePageToEncoding` (`data-model/lib/index.d.ts`).

---

## C. 12개 필수 사실

### 1. 모델공간 엔티티 열거와 필드 — 확인됨

```ts
const db = docManager.curDocument.database                 // AcDbDatabase
for (const e of db.tables.blockTable.modelSpace.newIterator()) {
  e.objectId       // 핸들 문자열 (DXF 그룹 5) — 예 '10A'
  e.dxfTypeName    // 'LINE' | 'LWPOLYLINE' | 'INSERT' | 'DIMENSION' …
  e.type           // 'Line' | 'Polyline' | 'BlockReference' | 'RotatedDimension'
  e.layer          // 레이어명
  e.ownerId        // 소유 BlockTableRecord 핸들
  e.geometricExtents  // AcGeBox3d
}
db.tables.blockTable.modelSpace.newIterator().count        // 9 (실측)
```

- 반복자 타입 `AcDbObjectIterator<AcDbEntity>`(`data-model/lib/misc/AcDbObjectIterator.d.ts`)에 `count` 게터가 있다.
- **타입 판별자 주의.** `AcDbEntity`의 JSDoc은 "removing the `AcDb` prefix from the constructor name"이라 적었지만 **구현은 `get type() { return this.constructor.typeName }`** (정적 필드). 즉 minify에 안전하다. 실측(minified CJS 번들)에서 `constructor.name`은 `Qr`/`gn`이었지만 `type`은 `Line`/`Polyline`으로 정상이었다. 단 `DIMENSION`은 `type = 'RotatedDimension'`, `dxfTypeName = 'DIMENSION'`이므로 **DXF 타입별 통계 키는 `dxfTypeName`을 써야 한다**(ADR-0002 §6 교차검증).
- 다른 공간: `for (const btr of db.tables.blockTable.newIterator())` → `btr.name`(`*Model_Space`/`*Paper_Space`/블록명), `btr.objectId`, `btr.newIterator()`, `btr.isModelSapce` / `btr.isPaperSapce`(오타는 상류 그대로), `btr.isXref`, `btr.isUnresolvedXref`, `btr.pathName`.
- 레이어: `db.tables.layerTable.newIterator()` → `AcDbLayerTableRecord { name, objectId, isOff, isFrozen, isLocked, lineWeight, linetype, color, isPlottable, transparency, description }`.
- 텍스트: `AcDbText.textString`, `AcDbMText.contents`(원본 제어코드 보존 — 실측 `"지하 1층 평면도\P축척 1:100\P{\C1;검토자 홍길동}"`).
- INSERT: `AcDbBlockReference { blockName, position, rotation, scaleFactors, normal, columnCount/rowCount/columnSpacing/rowSpacing, blockTableRecord, blockTransform: AcGeMatrix3d, attributeIterator(): AcDbObjectIterator<AcDbAttribute> }`.
  실측: 회전 30°·스케일 1.5의 INSERT `106`에서 `blockTransform.elements = [1.29903…, 0.75, 0,0, -0.75, 1.29903…, 0,0, 0,0,1,0, 220,10,0,1]`(열 우선 4×4), 속성 `{ tag: 'TITLE', value: '대명건설 신축공사', handle: '107' }`.
  **ATTRIB/SEQEND는 모델공간 반복자에 나오지 않는다**(INSERT 소유). 핸들 `107`/`108`은 최상위 카운트 9에 포함되지 않는다 → 엔진 `stats.py`와 카운트 정의를 맞출 때 주의.
- DIMENSION: `AcDbDimension { dimBlockId, measurement, dimensionStyleName, dimensionText, textPosition }`. 실측 `dimBlockId='*D1'`, `measurement=100`.
- 페이퍼공간 실측: VIEWPORT 2 + LINE 1. `AcDbEntity`는 DXF 그룹 67을 `_dxfPaperSpace`로 보관하지만 공개 게터는 없다 — **공간 구분은 `ownerId` → BlockTableRecord 이름으로 판단해야 한다**(NDJ `provenance.space`).

### 2. 레이어별 통계에 필요한 기하 접근 — 확인됨(길이는 우회 필요)

| 값 | API | 실측 |
|---|---|---|
| 해치 면적 | `AcDbHatch.area` | `3600` (정확) |
| 해치 패턴 | `AcDbHatch.patternName` | `'SOLID'` |
| 폴리라인 면적 | `AcDbPolyline.area` | `26988.4808392102` |
| 원 면적 | `AcDbCircle.area` | `1256.6370614359173` |
| 원/호 반지름 | `AcDbCircle.radius` / `AcDbArc.radius`, `startAngle`, `endAngle`(라디안) | 20 / 25, 0, π/2 |
| 선 길이 | `AcDbLine.startPoint.distanceTo(AcDbLine.endPoint)` | `200` |
| bbox | `AcDbEntity.geometricExtents: AcGeBox3d` | — |

**곡선 길이 게터가 없다.** `AcDbCurve`에는 `closed`/`area`만 abstract로 있고 `length`가 없다. 공개 경로는 두 가지이며 실측에서 **같은 값**을 냈다:

```ts
// (a) 교차 프리미티브 합산 — 모든 커브 공통
function curveLength(e: AcDbEntity): number {
  let total = 0
  for (const p of (e as AcDbCurve).subGetIntersectCurves()) {   // AcGeIntersectPrimitive[]
    if (p.kind === 'line') total += p.line.length               // AcGeLine3d.length
    else if (p.kind === 'circArc') total += p.arc.length        // AcGeCircArc3d.length
    else if (p.kind === 'ellipseArc') total += p.arc.length
    else if (p.kind === 'spline') total += p.spline.length
  }
  return total
}

// (b) 속성 인스펙터 스키마에 계산된 length 가 들어 있다
const geom = e.properties.groups.find(g => g.groupName === 'geometry')
geom?.properties.find(p => p.name === 'length')?.accessor.get()
```

실측: 벌지 0.5를 가진 닫힌 폴리라인 `101`의 길이 = **631.8238045004031** (두 경로 동일, 해석해 `200+100+125·4·atan(0.5)+100`과 일치). 레이어 `A-WALL` 합계 = `871.093713` (LINE 200 + 폴리라인 631.8238 + ARC 39.2699).

**속성 API(선택·특성 패널의 기반, W4-01).** `AcDbEntity.properties: AcDbEntityProperties { type, groups: AcDbEntityPropertyGroup[] }`, 각 항목 `AcDbEntityRuntimeProperty { name, type: 'array'|'string'|'int'|'float'|'enum'|'color'|'transparency'|'layer'|'linetype'|'lineweight'|'boolean', editable?, options?, itemSchema?, accessor: { get(), set?(v) } }`. 폴리라인 실측 그룹: `general`(handle/color/layer/linetype/linetypeScale/lineWeight/transparency), `geometry`(vertices 배열 — `{x,y,bulge,startWidth,endWidth}`, elevation, length), `others`(closed).

### 3. 히트테스트·박스 선택·하이라이트·줌 — 확인됨

```ts
const view = docManager.curView                      // AcTrView2d

view.pick(point: AcGePoint2dLike, hitRadiusPx?: number, pickOneOnly?: boolean)
  : AcEdSpatialQueryResultItemEx[]                   // { minX,minY,maxX,maxY,id, children? }
view.search(box: AcGeBox2d | AcGeBox3d, options?: AcTrSpatialSearchOptions)
  : AcEdSpatialQueryResultItemEx[]
view.select(point?: AcGePoint2dLike)                 // pick + selectionSet.add
view.selectByBox(box: AcGeBox2d)                     // = selectByBoxWithMode(box, 'crossing', 'add')
view.selectByBoxWithMode(box, mode: AcEdSelectionMode, action?: AcEdSelectionAction)  // AcEdBaseView
view.highlight(ids: AcDbObjectId[]) / view.unhighlight(ids)
view.zoomTo(box: AcGeBox2d, margin?: number)
view.zoomToFitDrawing(timeout?: number, layoutBtrId?: AcDbObjectId)
view.zoomToFitLayer(layerName: string): boolean
view.flyTo(point: AcGePoint2dLike, scale: number)
view.screenToWorld(p) / view.worldToScreen(p)        // AcGePoint2d
view.selectionSet                                    // AcEdSelectionSet
```

- **좌표계 주의:** `pick`의 `point`는 **월드 좌표**, `hitRadius`는 **픽셀**이다(`AcEdBaseView.pick` JSDoc). 화면 좌표는 `screenToWorld()`로 먼저 변환한다.
- 실측: `pick({x:50,y:30}, 8)` → `['102','109']`(원 둘레 + 해치 내부). `search(0..210 × 0..160)` → 9개 전부. `selectByBox` 후 `selectionSet.ids` 9개.
- `AcEdSelectionSet`: `ids: string[]`, `count`, `add(id|ids)`, `delete(id|ids)`, `has(id)`, `clear()`, 이벤트 `events.selectionAdded` / `events.selectionRemoved`(`AcEdSelectionEventArgs { ids }`).
- 대화형 선택은 `AcEditor.getSelection(AcEdPromptSelectionOptions)` / `selectAll(filter?: AcEdSelectionFilter)`.
- 공간 인덱스 구현은 교체 가능: `AcTrRBushSpatialIndex` / `AcTrHierarchicalSpatialIndex` / `AcTrLinearSpatialIndex` (`lib/spatialIndex/`).

### 4. 이벤트 — 확인됨(단, "렌더 완료" 이벤트는 없음)

| 소스 | 이벤트 |
|---|---|
| `AcApDocManager.events` | `documentToBeOpened`, `documentCreated`, `documentActivated`, `documentToBeActivated`, `documentToBeDestroyed`, `documentDestroyed`, `workersReady` — 인자 `AcDbDocumentEventArgs { doc: AcApDocument; mode: AcEdOpenMode }` |
| `AcTrView2d.events`(← `AcEdBaseView`) | `mouseMove`, `viewResize`, `viewChanged`, `hover`, `unhover`, `renderFrame` |
| `AcTrView2d.selectionSet.events` | `selectionAdded`, `selectionRemoved` |
| `AcEditor.events` (`docManager.editor`) | `sysVarChanged`, `commandWillStart`, `commandEnded` (`AcEdCommandEventArgs { command }`) |
| `AcDbDatabase.events` | `entityAppended`, `entityModified`, `entityErased`, `layerAppended`, `layerModified`, `layerErased`, `dictObjetSet`, `dictObjectErased`, `openProgress`, `openFailed` |
| 전역 `eventBus` (mitt) | `open-file`, `open-local-file-started`, `open-file-progress`, `failed-to-open-file`, `cache-font`, `font-file-selected`, `close-layer-manager`, `message`, `fonts-not-found`, `fonts-not-loaded`, `failed-to-get-avaiable-fonts`, `font-not-found`, `missed-data-changed`, `undo-stack-changed`, `session-db-edit-committed`, `busy-indicator` |

- 이벤트 매니저 API: `AcCmEventManager<T>.addEventListener(fn)` (data-model 재수출). 전역 버스는 `mitt`의 `on/off/emit`.
- **`AcApDocManager.events`는 `readonly` 객체 필드**라 `docManager.events.documentActivated.addEventListener(...)` 형태로만 붙는다.
- 렌더 완료: 단일 이벤트가 없다. `AcTrView2d.waitUntilIdle(timeoutMs?): Promise<boolean>`, `isProcessingEntities`, `isDirty`, `progressiveOpenStats`를 쓴다. 실측에서 `openDocument()` 직후 `waitUntilIdle(30000)`으로 안정적으로 대기했다.
- 실측 순서(픽스처): `workersReady(69ms) → documentToBeOpened(253) → documentActivated(301) → documentCreated(1496)`. **`documentCreated`가 `documentActivated` 뒤에 오는 경우가 있다** — MDI 탭 UI는 `documentActivated`만 신뢰하고 `documentCreated`로 탭을 만들면 순서가 어긋난다.

### 5. transient 오버레이와 마크업 — 확인됨(비동기 주의)

```ts
view.addTransientEntity(entity: AcDbEntity | AcDbEntity[]): void
view.removeTransientEntity(objectId: AcDbObjectId): void
view.setTransientEntityVisible(objectId: AcDbObjectId, visible: boolean): void
view.cadScene.setTransientEntityVisible(objectId, visible): boolean   // AcTrScene — 성공 여부 반환
```

- **`addTransientEntity()`는 fire-and-forget 비동기다.** 번들 구현이 `drawEntity(...).asyncDraw().then(() => scene.addTransientEntity(...))`이고 Promise를 반환하지 않는다. 즉 호출 직후에는 씬에 없다(실측: 500 ms 후 `AcTrScene.setTransientEntityVisible` → `true`). CadHost는 자체 완료 신호를 만들어야 한다.
- `AcTrView2d.hasEntity(objectId)`는 **변환된 DB 엔티티만** 본다. transient에는 언제나 `false`(실측).
- 미리보기(이동/복사 잼용): `canCreateEntityPreview(ids)`, `createEntityPreview(ids): string|null`, `updateEntityPreview(handle, AcGeMatrix3d)`, `removeEntityPreview(handle)`, `updateTransientPreviewTransforms([{objectId, matrix}])`.
- 오버레이 데이터베이스(참조 도면·비교용): `AcApDocManager.loadOverlay(fileName, content, options) → overlayId`, `registerOverlayDatabase(db)`, `setOverlayVisible`, `removeOverlay`, `clearOverlays(view?)`, `getOverlayIds(view?)`, `getOverlayLayout(id)`, `setCompareDisplay(AcApCompareDisplayOptions, view?)`, `setOverlayCompareDisplay(overlayId, options, view?)`.
  **제약(상류 JSDoc):** 오버레이 지오메트리는 최상위 엔티티만 그린다 — "block (INSERT) expansion, viewports, and dimensions are not yet supported and are skipped".

**마크업 사이드카 JSON 형식** (`lib/command/markup/AcApMarkupTypes.d.ts`, `AcApMarkupSidecar.d.ts`):

```ts
interface AcApMarkupSidecarFile { version: 1; drawingName?: string; markups: AcApMarkupRecord[] }
type AcApMarkupRecord = AcApMarkupMeta & { geometry: AcApMarkupGeometry }
interface AcApMarkupMeta {
  id: string
  type: 'text'|'line'|'arrow'|'cloud'|'rect'|'circle'|'highlight'|'callout'|'stamp'|'symbol'
  layoutId?: string                       // 레이아웃 BTR id, 없으면 모든 레이아웃에 표시
  style: { color: string; lineWeight?: number; fontSize?: number }
  text?: string
  comment: string
  status: 'open'|'question'|'answered'|'closed'
  author: string; createdAt: string; updatedAt: string
}
// 헬퍼: parseMarkupSidecar(text), stringifyMarkupSidecar(file), markupSidecarFileName('plan.dwg') → 'plan.markup.json'
```

기하는 **DWG 엔티티가 아니라 뷰 로컬(HTML/CAD transient)** 이다(타입 파일 상단 주석). 측정 쪽도 대칭 구조: `parseMeasurementSidecar` / `stringifyMeasurementSidecar` / `measurementSidecarFileName`, 저장소 `AcApMeasurementStore` / `AcApMarkupStore`, 히스토리 `AcApMarkupHistory` / `AcApMeasurementHistory`.

명령: 마크업 14개(`MARKUPTEXT/LINE/ARROW/CLOUD/RECT/CIRCLE/HIGHLIGHT/CALLOUT/STAMP/VIS`, `CLEARMARKUPS`, `MARKUPEXPORT/IMPORT`, `REVCLOUD`), 측정 11개(`MEASUREDISTANCE/AREA/ANGLE/ARC/POINT`, `CLEARMEASUREMENTS`, `MEASUREMENTVIS/EXPORT/IMPORT/COLOR`, `MEASUREMENT`).

### 6. 편집 트랜잭션과 undo/redo — 확인됨

```ts
import { acapRunDatabaseEdit } from '@mlightcad/cad-simple-viewer'

acapRunDatabaseEdit(db, 'W4-03: move', () => { /* … */ })   // undo mark + 'undo-stack-changed' emit
db.runDatabaseEdit(label, fn)                                // 데이터 모델 레벨

const tm = db.transactionManager                             // AcDbDatabaseTransactionManager
tm.startTransaction() / tm.commitTransaction() / tm.abortTransaction()
tm.startUndoMark(label?) / tm.endUndoMark() / tm.cancelUndoMark()
tm.undo(): boolean / tm.redo(): boolean / tm.canUndo() / tm.canRedo() / tm.clearUndoStack()
tm.strictMode: boolean
```

- 실측: 모델공간 9 → `acapRunDatabaseEdit`으로 LINE append → 10 → `undo()` → 9 → `redo()` → 10. `undo()`/`redo()` 모두 `true` 반환.
- 변경 기록 타입: `AcDbDatabaseChange = {kind:'modify'|'append'|'remove'|'sysvar', …}`, 컨테이너 `AcDbChangeContainer = {type:'blockTableRecord'|'symbolTable'|'dictionary', …}`, 적용기 `AcDbChangeApplier.applyForward/applyInverse`, 헬퍼 `acdbCollectChangeEntities`.
- 앱 레벨 편집 서비스(트랜잭션 포함): `AcApDocument.entityService: AcApEntityService`
  `getEntitiesByIds(ids)`, `transformEntities(entities, AcGeMatrix3d)`, `translateEntities(entities, displacement)`, `rotateEntities(entities, basePoint, angleRad)`, `cloneAndTransform(entities, matrix, { append? })`, `eraseEntities(objectIds)`, `moveEntitiesToCurrentLayer(objectIds)`, `runEdit(label, fn)`, `runEntityEdit(fn)`, 정적 `AcApEntityService.copyDisplayTraits(source, target)`.
  실측: 이동/회전/복제/삭제 각 1건 성공, 각각 하나의 undo 마크가 된다.
- 명령: `UNDO`(별칭 `U`), `REDO`. 명령 객체에는 `AcEdCommand.recordsUndoStack: boolean`가 있다.
- 쓰기 게이트: `AcEdOpenMode { Read = 0, Review = 4, Write = 8 }`. `AcApDocManager.lookupGlobalCmd()`는 현재 문서 모드와 호환되는 명령만 돌려준다. 편집 명령은 전부 `Write`.

### 7. `AcDbDatabase.dxfOut()` — 확인됨 (ADR-0002 2차 변환 경로: **합격**)

```ts
dxfOut(
  _fileName?: string,                       // ObjectARX 호환용, 무시됨
  precision?: number,                       // DXF filer 자릿수
  version?: AcDbDwgVersion | string | number,
  optionsOrThumbnail?: boolean | { saveThumbnailImage?: boolean; format?: 'ascii' | 'binary' }
): string | Uint8Array
```

`data-model/lib/database/AcDbDatabase.d.ts:1190`. 뷰어 명령 `CDXF`(`AcApConvertToDxfCmd` → `AcApDxfConvertor`)가 같은 경로를 쓴다.

#### 7.1 픽스처 왕복 (같은 파일을 다시 열어 비교)

| 항목 | 원본 | `dxfOut()` 후 재-open | 결과 |
|---|---|---|---|
| 모델공간 최상위 엔티티 | 9 | 9 | 일치 |
| LINE / LWPOLYLINE / CIRCLE / ARC | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 | 일치 |
| TEXT / MTEXT / INSERT / HATCH / DIMENSION | 1 / 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 / 1 | 일치 |
| 엔티티 핸들 집합 | `100,101,102,103,104,105,106,109,10A` | 동일 | **보존됨** (누락 0, 신규 0) |
| 레이어(이름#핸들) | `0#10, A-WALL#11, A-TEXT#12, A-HATCH#13, 치수#14` | 동일 | **보존됨** |
| 블록(이름#핸들) | `*Model_Space#1E, *Paper_Space#1F, TITLEBLK#20, *D1#21` | 동일 | **보존됨** |
| ATTRIB | `TITLE = 대명건설 신축공사` (핸들 `107`) | 동일 | **보존됨** |
| 한글 TEXT/MTEXT | `대명건설 도면`, `지하 1층 평면도\P…` | 동일 | **보존됨** |
| 레이아웃 | `Model`, `Layout1` | 동일 | 보존됨 |
| `$ACADVER` | AC1032 | AC1032 (요청대로), `'AC1015'` 요청 시 AC1015 | 버전 지정 동작 |
| 출력 크기 / 시간 | 10 736 B | ASCII 10 450 B (3 ms), binary 11 788 B (`Uint8Array`) | — |
| 섹션 | HEADER/TABLES/BLOCKS/ENTITIES/OBJECTS | 동일 | `CLASSES`는 원본에 클래스가 없으면 생략, `THUMBNAILIMAGE`는 옵션 |

Node(헤드리스, minify된 CJS 번들)에서 동일 결과: 10 554 B, 핸들·레이어·블록 전부 보존.

#### 7.2 실제 DWG 왕복 (canteen.dwg, AC1014, 2.6 MB)

| 항목 | 값 |
|---|---|
| libredwg 워커 파싱 + 변환 | 2 230 ms (파싱) / 2 825 ms (렌더 idle까지) |
| 모델공간 엔티티 | **25 122** |
| 타입 분포 | LINE 22 835, INSERT 690, ARC 516, LWPOLYLINE 359, HATCH 274, MTEXT 188, TEXT 106, CIRCLE 97, DIMENSION 28, SPLINE 25, WIPEOUT 3, ELLIPSE 1 |
| `dxfOut('…', 6, 'AC1032')` | 84 ms, 6 623 024 B ASCII |
| 그 DXF를 다시 파싱 | 모델공간 **25 122** (일치) |

**결론:** `dxfOut()`은 ADR-0002 §3의 2차 변환 경로로 **쓸 수 있다.** 엔티티 수와 핸들이 보존되고, DWG(AC1014) → DXF(AC1032) 변환이 25 k 엔티티에서 84 ms다.
남은 검증(W2-06/W2-05 소관): (a) 엔진 ezdxf가 이 출력물을 읽는지, (b) XDATA·확장 딕셔너리·프록시 엔티티 보존, (c) 대용량(100 k+)에서의 메모리, (d) acad-ts 출력과의 비교. 여기서는 **엔티티·핸들·레이어·블록·한글 텍스트 수준까지만** 확인했다.

**주의:** `openDocument()`에 넘긴 `ArrayBuffer`는 **DWG 경로에서 워커로 transfer되어 detach된다**(실측: 호출 후 `byteLength === 0`). 원본 바이트를 뒤에서 다시 써야 하면 미리 복사해 둘 것. DXF 경로에서는 detach되지 않았다.

### 8. 레이아웃(페이퍼 공간)과 뷰포트 드릴다운 — 확인됨

```ts
db.objects.layout                                    // AcDbLayoutDictionary
for (const l of db.objects.layout.newIterator())     // AcDbLayout
  l.layoutName, l.tabOrder, l.blockTableRecordId, l.limits, l.extents, l.viewportArray

docManager.setActiveLayout(view?, database?)
view.activeLayoutBtrId = paperSpaceBtrId             // 레이아웃 전환
view.activeLayoutView                                // AcTrLayoutView
view.modelSpaceBtrId
```

- 실측: `Model`(tabOrder 0, BTR `1E`) / `Layout1`(tabOrder 1, BTR `1F`). `activeLayoutBtrId`를 `1F`로 바꾸면 그대로 반영된다.
- 레이아웃 뷰 관리자: `AcTrLayoutViewManager { activeLayoutBtrId, activeLayoutView, has(id), getAt(id), add(view), resize(w,h), render(scene) }`.
- 레이아웃 전환 이벤트: `acdbHostApplicationServices().layoutManager.events.layoutSwitched` (`data-model/lib/object/layout/AcDbLayoutManager.d.ts:52`, 인자 `AcDbLayoutEventArgs`). `AcTrView2d`가 이미 구독해 레이아웃 뷰를 만들고 초기 줌을 적용한다. 관리자 API: `countLayouts()`, `findLayoutNamed(name)`, `findActiveLayout()`, `setCurrentLayoutId(id)`.
- 뷰포트 엔티티: `AcDbViewport { number, centerPoint, width, height, viewCenter, viewTarget, viewDirection, viewHeight … }`. 실측 `200`(number 1, 297×420 — 페이퍼 전체), `201`(number 2, 180×240, viewCenter (100,50)).
- **드릴다운은 `pick()`에 내장돼 있다.** `AcTrView2d.pick` JSDoc: 페이퍼 공간에서 뷰포트 사각형 내부를 클릭하면 그 뷰포트가 보여주는 **모델공간 엔티티**가 잡히고(`pickThroughViewports`, 뷰포트별 카메라로 각각 레이캐스트), 테두리 근처를 클릭하면 `AcDbViewport` 자체가 잡힌다. 데스크톱 AutoCAD의 MSPACE/PSPACE·CVPORT 모델은 **구현하지 않는다**고 명시.
- **주의:** 픽스처의 `AcDbLayout.viewportArray`가 빈 배열로 읽혔다(내 DXF가 그룹 331을 쓰지 않음). 뷰포트 목록은 `viewportArray`가 아니라 **페이퍼공간 BTR을 순회해 `AcDbViewport`를 걸러서** 만드는 편이 안전하다.

### 9. XREF — 조건부 (자동 해석 없음, 수동 API 있음)

- **자동 해석은 하지 않는다.** 뷰어는 외부 참조 파일을 스스로 가져오지 않는다. 미해결 참조는 `AcTrView2d.missedData.xrefs: { name: string; pathName: string; isOverlay: boolean }[]`에 모이고 `missed-data-changed` 이벤트가 뜬다. 블록 레코드 쪽에도 `AcDbBlockTableRecord.isXref / isOverlayReference / isUnresolvedXref / pathName`가 있다.
- 수동 attach:

```ts
import { AcApXrefManager } from '@mlightcad/cad-simple-viewer'

const session = await AcApXrefManager.instance.attachOverlay({
  blockName, fileName, content /* ArrayBuffer */ | sourceDb, sourcePath,
  transform?: { position, scale, rotationRad }, insertId?
})   // → AcApXrefSession { id, blockName, insertId?, overlayId, sourcePath, visible }

AcApXrefManager.instance.sessions            // readonly AcApXrefSession[]
  .getSession(id) / .getSessionByBlockName(name)
  .setVisible(id, v) / .setVisibleByBlockName(name, v)
  .unload(id) / .unloadByBlockName(name) / .clearAll()
AcApXrefManager.createHostXrefInsert(hostDb, blockName, pathName, transform, origin?)
  // → { record: AcDbBlockTableRecord, insert: AcDbBlockReference }
```

- 명령 `XATTACH`(별칭 `XA`, `AcApXAttachCmd`).
- **중요한 제약:** attach는 내부적으로 `AcApDocManager.loadOverlay`/`registerOverlayDatabase` 위에 있고, 오버레이 지오메트리는 INSERT 전개·뷰포트·치수를 **건너뛴다**. 즉 XREF 안의 블록 참조와 치수는 화면에 나오지 않는다.
  → **W3-06과 ADR-0002 §1의 결론을 강화한다: XREF는 정본 DXF 단계에서 `ezdxf.xref`로 임베드하고, 뷰어의 XREF 세션은 "임베드 전 미리보기/언로드 토글" 용도로만 쓴다.**

### 10. MDI(다중 문서) — 확인됨

```ts
docManager.documents: AcApDocument[]      // 탭 순서
docManager.documentCount
docManager.document(index)
docManager.activeSessionId
docManager.curDocument / docManager.mdiActiveDocument
docManager.sessionFor(doc): AcApDocSession | undefined
await docManager.activateDocument(doc): Promise<boolean>
await docManager.closeDocument(doc?): Promise<boolean>   // 마지막 문서를 닫으면 새 Untitled로 대체
docManager.ensureSplitView(container): AcTrView2d        // 두 번째 캔버스
await docManager.openDocument(name, buf, options, view?) // view로 대상 캔버스 지정
```

- 실측: 두 문서(UTF-8 R2018 + CP949 R2000)를 동시에 열고 `activateDocument(document(0))` → `true`. 두 DB에서 각각 한글 텍스트·레이어명이 정확히 읽힌다.
- 세션: `AcApDocSession { id, context, overlays: Map<string, {db, layout}>, viewState?, doc }`. 탭 MDI에서는 **캔버스 하나를 공유**하고 `AcTrView2d.captureSessionState()/restoreSessionState()/beginNewSession()/disposeSessionState()`로 씬을 파킹한다.
- `attachSatelliteView`/`detachSatelliteView`는 `@deprecated`. `ensureSplitView`를 쓴다.
- 문서 정리: `AcApDocument.destroy()`, `AcApDocManager.destroy(): Promise<void>`(뷰 파기 + 플러그인 언로드).

### 11. Node 헤드리스 — 조건부

- **`cad-simple-viewer-cli` 같은 패키지는 npm에 없다.** 브리프가 언급한 이름은 확인되지 않았다.
- **`@mlightcad/data-model`은 Node에서 CommonJS로만 로드된다.**
  - `import('@mlightcad/data-model')` → `ERR_UNSUPPORTED_DIR_IMPORT` (ESM 엔트리 `lib/index.js`가 확장자 없는 디렉터리 임포트를 쓴다. 번들러 전용).
  - `require('@mlightcad/data-model')` → 정상. 417개 export.
  - `require('@mlightcad/data-model/package.json')` → `ERR_PACKAGE_PATH_NOT_EXPORTED` (`exports` 맵에 없음).
- 헤드리스로 되는 것(실측, `scripts/probe-node.cjs`): DXF 읽기(10 ms), 레이어/블록/모델공간 열거, `dxfTypeName`·핸들·기하, `dxfOut()` 왕복, CP949 디코딩.
- **되지 않는 것:** `cad-simple-viewer`(DOM·WebGL·`document` 필요), MTEXT 렌더(웹워커·three), 따라서 화면 기반 통계·PNG 출력. libredwg-converter의 DWG 파싱도 워커 전용이라 Node에서는 별도 배선이 필요하다.
- **결론:** `statsByLayer` 상당의 통계는 **Node에서 data-model만으로 산출 가능**하다. 그러나 `packages/cad-core`는 `data-model`을 ESM으로 임포트해야 하므로 Electron 메인/utilityProcess에서 쓰려면 **번들링(electron-vite rollup)이 필수**다. 순수 `node script.js`는 CJS 경로로만 동작한다.

### 12. WASM 메모리와 DWG 로딩 시간 — 조건부

| 항목 | 값 |
|---|---|
| `libredwg-web.wasm` 크기 | 9 960 337 B (인라인 아님, 워커 형제 파일) |
| `libredwg-parser-worker.js` | 193 649 B |
| `mtext-renderer-worker.js` | 1 182 527 B |
| canteen.dwg(2.6 MB, AC1014) 파싱 | 2 230 ms |
| 렌더 idle까지 | 2 825 ms |
| 모델공간 엔티티 | 25 122 (렌더 결과: `docs/spikes/img/sample-dwg-canteen.png`) |
| 워커 옵션 | `AcDbDatabaseConverterConfig { parserWorkerUrl?, timeout?, useWorker?, convertByEntityType?, progress? }` |
| 읽기 옵션 | `AcDbDatabaseConverterReadOptions { minimumChunkSize?, progress?, timeout?, sysVars? }` |

- WASM 힙 크기 옵션은 **공개 API에 없다.** `AcDbLibreDwgConverter`/`AcDbDatabaseConverterConfig` 어디에도 메모리 설정이 없고, emscripten 모듈 설정도 워커 내부에 갇혀 있다. OOM 대응은 옵션이 아니라 **파일 크기 게이트**로 해야 한다(ADR-0002 §4의 60 MB 미리보기 상한과 일치).
- OOM 진단 훅은 있다: `AcDbDatabase.lastOpenError: AcDbOpenDatabaseError | null`, 타입 `AcDbOpenDatabaseErrorCode`, 이벤트 `failed-to-open-file { fileName, errorCode?, errorMessage? }`. `AcDbDatabase` JSDoc이 "worker out-of-memory"를 구분 용도로 명시한다.
- 진행률: `AcDbConversionProgressCallback(percentage, stage, stageStatus, data?, error?)`, 전역 `open-file-progress` 이벤트(`AcDbProgressdEventArgs`), 메모리 추정 `acdbEstimateDatabaseMemory` / `acdbFormatMemoryEstimate`(data-model), `AcTrMTextRenderer.estimateMemoryUsage()`.
- **피크 RSS는 측정하지 않았다.** headless Chromium의 `performance.memory`는 값이 고정돼 나온다(실측 delta 0). 실측은 **W2-06 소관**이며 이 스파이크의 숫자를 대용량 임계값 결정에 쓰면 안 된다.

---

## D. 그 밖에 W3-02가 알아야 할 사실

### D.1 패키징 결함 3건 (실측)

1. **`@mlightcad/cad-simple-viewer@1.6.3`의 타입이 미선언 의존성을 참조한다.**
   - `lib/editor/global/eventBus.d.ts:2` → `import { type Emitter } from 'mitt'`
   - `lib/index.d.ts:11`, `lib/editor/input/ui/index.d.ts:5`, `lib/editor/input/ui/AcEdMTextEditor.d.ts:2` → `@mlightcad/mtext-input-box`
   `dependencies`/`peerDependencies` 어디에도 없다. `skipLibCheck: false`로 컴파일하면 `TS2307`로 실패한다.
   **런타임은 영향 없다.** ESM 번들 `dist/cad-simple-viewer.js`의 bare import는 `@mlightcad/data-model`, `@mlightcad/mtext-renderer`, `@mlightcad/three-renderer`, `lodash-es`, `three`(+`three/examples/jsm/*` 5개)뿐이고 `mtext-input-box`는 인라인돼 있다.
2. **`@mlightcad/data-model@1.14.3`의 `lib/entity/AcDbEntity.d.ts:388`이 임포트되지 않은 타입(`AcGePoint3dLike`, `AcDbObjectId`)을 쓴다.** `skipLibCheck: false`에서 `TS2552` 4건.
3. **`@mlightcad/three-renderer@1.6.3`의 `lib/viewport/AcTrBaseView.d.ts:3`이 확장자 없는 `three/examples/jsm/controls/OrbitControls`를 임포트**해 `@types/three@0.172.0`(bundler resolution)에서 해석되지 않는다.

→ **`packages/cad-core`는 `skipLibCheck: true`가 필요하다**(스파이크에서 `true`면 `tsc --noEmit` 통과, `false`면 실패). CLAUDE.md의 "TypeScript strict"와 충돌하지 않지만 예외를 ADR/tsconfig 주석에 남겨야 한다. `mitt`는 명시 의존성으로 추가하는 편이 안전하다(MIT).

### D.2 명령 스택

```ts
docManager.commandManager                    // AcEdCommandStack
  .addCommand(groupName, globalName, localName, cmd, alias?)
  .lookupGlobalCmd(name, mode?) / .lookupLocalCmd(name, mode?)
  .searchCommandsByPrefix(prefix, mode?)     // AcEdCommandIteratorItem { commandGroup, command }
  .iterator()                                // IterableIterator<AcEdCommandIteratorItem>
  .removeCmd(group, name) / .removeGroup(group) / .removeAll()
  .activeCommand / .cancelActive() / .getCommandAliases(cmd, group?)
docManager.sendStringToExecute(cmdStr)                 // 동기 트리거(비동기 완료 대기 없음)
await docManager.executeCommandString(cmdStr)          // 첫 줄 = 명령명, 나머지 줄 = 프롬프트 입력
await docManager.runScript(scriptText)                 // AutoCAD .scr 다중 명령
docManager.searchCommandsByPrefix(prefix)
AcApDocManagerOptions.commandAliases = { LINE: ['L','LN'], CIRCLE: 'CI' }   // 별칭 재정의
```

실측 등록 명령 수 **135**(그룹 `ACAD`). 전체 목록과 별칭·모드는 `docs/spikes/mlightcad-capabilities.md`.
자체 명령은 `AcEdCommand`를 상속해 `execute(context: AcApContext)`를 구현한다. 프롬프트는 `AcEditor.getPoint/getAngle/getDistance/getDouble/getInteger/getString/getKeywords/getEntity/getSelection/getBox`(모두 `AcEdPrompt*Options` → `AcEdPrompt*Result`).

### D.3 플러그인

```ts
docManager.pluginManager                      // AcApPluginManager
  .loadPlugin(plugin: AcApPlugin)             // { name, version?, description?, onLoad(ctx, cmdStack), onUnload(...) }
  .registerLazyPlugin({ name, triggers: string[], loader: () => AcApPlugin | Promise<AcApPlugin> })
  .isLazyPluginTrigger(t) / .getLazyPluginTriggers() / .loadByTrigger(t)
  .unloadPlugin(name) / .isPluginLoaded(name) / .getPlugin(name) / .getLoadedPlugins() / .unloadAllPlugins()
  .loadPluginsFromConfig(plugins, { continueOnError? })
  .loadPluginsFromFolder(folderPath, { pluginList?, continueOnError? })
```
`AcApDocManagerOptions.plugins.fromConfig` / `.fromFolder`로 초기화 시에도 지정할 수 있다.
**W4-03/W4-04의 자체 편집·생성 명령은 플러그인 하나로 묶어 등록하는 것이 버전 업그레이드에 가장 안전하다**(mlightcad가 같은 이름 명령을 추가하면 `addCommand`의 충돌 검사에 걸리므로 그룹 이름을 `DMCAD`로 분리한다).

### D.4 오픈 옵션

```ts
interface AcApOpenDatabaseOptions extends Omit<AcDbOpenDatabaseOptions, 'readOnly'> {
  mode?: AcEdOpenMode                 // Read 0 / Review 4 / Write 8
  progressiveRendering?: boolean      // 기본 false
  openViewMode?: AcApOpenViewMode     // 'extents' | 'saved'
  // 상속: minimumChunkSize?, drawNoPlotLayers?, …
}
```
`fontLoader` / `failOnFontLoadError`는 **제거됐다**(런타임에서 경고와 함께 무시). 폰트는 `FontManager.lazyFontLoading`으로 그리는 중에 지연 로드된다.

### D.5 레이어 서비스 (W3-04 입력)

`AcApDocument.layerService: AcApLayerService` — `getLayerSummaries()`, `createLayers(names)`, `setCurrentLayer`, `setLayerOn/Frozen/Locked/LineWeight/Plottable/Linetype/Transparency/Color/Description`, `setLayersVisibility/Frozen/Locked/Color`, `isolateLayers(names, mode)` / `unisolateFromSnapshot`, `deleteLayer(name)` / `restoreDeletedLayer`, `collectLayerEntities(name)`, `getEffectiveLayerTraits(name)`, 정적 `openLayerForWrite`, `resolveLayerTraits`.
문서 레벨 보조: `AcApDocument.layerStore`, `captureLayerPreviousState()`, `restoreLayerPreviousState()`, `isolateLayers/unisolateLayers`.

### D.6 뷰 정리와 리소스

`AcTrView2d`: `clear()`, `stopAnimationLoop()`, `captureSessionState()/restoreSessionState()/disposeSessionState()`, `stats`(`AcTrSceneStats`), `internalScene`/`internalCamera`(three 객체 직접 접근 — **격리 위반이므로 CadHost가 노출하지 않는다**).
`AcApDocManager.destroy(): Promise<void>`, `AcTrMTextRenderer.getInstance().dispose()` / `AcTrMTextRenderer.resetInstance()`, `UnifiedRenderer.terminateWorkers()`.
`AcApDocManager`, `AcDbDatabaseConverterManager`, `AcApXrefManager`, `FontManager`, `AcTrMTextRenderer`가 **모두 싱글턴**이다 → 테스트 격리와 문서 전환 시 상태 누수에 주의(W3-02 힙 증가 <10% 기준과 직결).
