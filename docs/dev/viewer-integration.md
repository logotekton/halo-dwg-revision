# 뷰어 통합 (CadHost · 창 배치 · 변환 · 레이어 가시성)

W3-02가 만들고 R1-00a가 병합·수복한 2D 뷰어 통합의 정본 문서다. 배경은
`docs/dev/cadhost-proposal.md`(파사드 설계), `docs/contracts/wave-3.md`(자산 배치·IPC 채널),
`docs/adr/0002-working-dxf.md`(변환 경로), 화면 C의 사용 규칙은
`docs/contracts/compare-dxf.md` §9다.

한 줄 요약: **mlightcad는 `packages/cad-core/src/mlightcad-surface.ts` 한 파일에만 있고,
그 위의 `CadHost`가 파사드이며, 렌더러는 `apps/web/src/features/viewer/host.ts`의 함수 일곱 개만
쓴다.** DWG 변환은 화면을 그리지 않는 숨김 창에서 따로 돈다.

## 1. 창과 프로세스 배치

```
Electron main (Node)
├── protocol handler  halocad://app/*        apps/desktop/src/main/protocol.ts
│     .wasm → application/wasm, HEAD 응답, Content-Length
├── main window       halocad://app/index.html
│     preload out/preload/index.js  →  window.halocad.{app,engine,files,viewer}
│     renderer: React 셸 + #viewer-root
│        └── CadHost (packages/cad-core)
│              ├── AcApDocManager  ─ mtext-renderer-worker.js   (MTEXT 글리프)
│              └── AcTrView2d      ─ WebGL 캔버스
├── viewer window     halocad://app/viewer.html      (개발·e2e 전용 단독 페이지)
│     같은 CadHost, 셸 없이 ViewerPanel만
└── convert window    halocad://app/convert.html     show:false, 요청마다 재사용
      preload out/preload/convert.js  →  window.halocadConvert (채널 2개뿐)
      renderer: convert-entry.ts
         └── libredwg-parser-worker.js + libredwg-web.wasm   (GPL)
```

- **왜 숨김 창인가.** mlightcad의 DWG 변환기는 `useWorker: true`를 강제하고 Node에는 `Worker`
  전역이 없다(ADR-0002 개정 §2). utilityProcess에서는 DWG를 못 연다. Web Worker와
  `WebAssembly.instantiateStreaming`, 커스텀 스킴이 모두 있는 가장 작은 컨텍스트가 숨김 렌더러다.
- 변환 창은 요청마다 재사용하고 **5분 유휴 뒤 파괴**한다. 한 번에 한 요청만 돌린다(20만 엔티티
  파싱 두 개가 한 렌더러 힙을 나눠 쓰면 OOM).
- 변환 창의 preload는 메인 창과 **다른 파일**이다. GPL 파싱 경로에 결함이 생겨도 엔진 연결·파일
  대화상자 같은 나머지 IPC 표면에 닿지 못한다. `contextIsolation: true`, `sandbox: true`.
- 렌더러가 죽으면(`render-process-gone`) 진행 중 요청을 전부 즉시 실패시키고 창을 버린다.
  그래야 호출자가 10분 타임아웃을 기다리지 않고 acad-ts 폴백으로 넘어간다.

## 2. 자산 경로

`halocad://app/viewer/` 아래에 워커·wasm·폰트가 있다(`window.halocad.viewer.assetsBase()`가
IPC로 알려준다 — 패키징이 위치를 바꿔도 `apps/web`을 다시 빌드하지 않게).

| 경로 | 내용 | 출처 |
|---|---|---|
| `viewer/workers/libredwg-parser-worker.js` | DWG 파서 워커 | GPL, 빌드 시 복사 |
| `viewer/workers/libredwg-web.wasm` | 파서 wasm (형제 파일이어야 한다) | GPL, 빌드 시 복사 |
| `viewer/workers/mtext-renderer-worker.js` | MTEXT 글리프 워커 | 빌드 시 복사 |
| `viewer/fonts/fonts.json` | 폰트 매니페스트(현재 Noto Sans KR 1종) | 커밋됨 |
| `viewer/fonts/*.woff·shx·ttf` | 폰트 파일 | **커밋 안 함** — W3-05 |

- 복사는 `pnpm --filter @halo-cad/web copy-viewer-assets`
  (`packages/dwg-io-gpl/scripts/copy-worker-assets.mjs`)가 하고, `dev`·`build` 스크립트가 먼저
  부른다. 약 11 MB의 서드파티 빌드 산출물이고 두 개는 GPL이므로 저장소에 넣지 않는다.
- `.wasm`은 반드시 `application/wasm`으로 나가야 `instantiateStreaming`이 받아준다. 스킴
  핸들러의 `assetHeaders()`가 그것과 `Content-Length`를 붙이고, `checkWorkersOnInit`의 **HEAD**
  요청에도 같은 헤더로 빈 본문을 답한다(HEAD에 답하지 않으면 뷰어가 영영 "workers not ready").
- CSP(`viewer.html`·`convert.html`): `script-src 'self' 'wasm-unsafe-eval'`,
  `worker-src 'self' blob:`, `img-src 'self' data: blob:`(MTEXT 글리프 아틀라스).

## 3. 변환 흐름 (DWG → 작업용 DXF)

```
엔진 WS  {"type":"convert.request", dwg_path, out_path}
   └→ main: halocad:convert:dwg-to-dxf   (렌더러/e2e도 같은 핸들러를 부른다)
        ├ readFile(dwg)                       ← 원본은 읽기만 한다 (CLAUDE.md 규칙 1)
        ├ 숨김 창에 bytes 전송
        │    convert-entry.ts:
        │      openDwg → repairDanglingReferences → exportDxf(dxfOut)
        │      → postProcessDxfOut  (INSERT 66 · HATCH 92 · LEADER dimstyle
        │                            · STYLE bigfont 0 · 핸들 유일성)
        │      → entityCount(0이면 실패로 판정 — libredwg가 조용히 85/200006만
        │         돌려준 실측이 있다)
        ├ writeFile(out_path)
        ├ acad-bridge info <dwg> --xrefs      ← dxfOut이 잃는 XREF 경로·TTF typeface
        └ 결과 {dxf_path, entity_count, converter, warnings, xrefs, styles}
   실패하면 → acad-ts 폴백(`acad-bridge dwg2dxf`), converter: "acad-ts"
             산출물을 고치지 않는다. 합격 판정은 엔진 교차검증이 한다(ADR-0002 개정 §4).
```

`--xrefs`는 W3-06이 만든 `acad-bridge`의 옵트인 플래그다. R1-00a 병합 전에는 W3-02가 같은 두 표를
`info.ts` 안에 따로 구현해 두었는데, 검증된 W3-06 쪽(`src/acad/xref-style-scan.ts`)을 남기고
데스크톱 변환기가 `--xrefs`를 붙여 부르도록 통일했다.

## 4. 상태 머신

`packages/cad-core/src/host/state-machine.ts`가 문서 하나의 수명을 정규화한다. 뷰어의 이벤트를
그대로 믿으면 안 되는 이유가 둘이다(실측).

- `documentCreated`가 `documentActivated`**뒤에** 올 수 있다(측정: toBeOpened 253ms →
  activated 301 → created 1496). 그래서 `created`는 문서를 **뒤로 되돌리지 않는다**.
- "렌더 끝" 이벤트가 없다. `waitUntilIdle()` 폴링 결과로 `rendering → ready`를 이 머신이 정한다.

```
        begin()                 activated/created         beginRender()
 (none) ────────▶ opening ──────────────────▶ parsed ──────────────▶ rendering
                    │                                                   │
                    │ fail()                              renderIdle()  ▼
                    └────────────▶ failed ◀── fail() ─────────────── ready
                                                    destroyed ──▶ closed
```

호스트 전체의 `status`(= `viewer` 스토어의 `status`)는 열려 있는 문서들 중 가장 나쁜 상태다:
`failed > opening > rendering > ready > idle`.

## 5. 레이어 가시성 API (화면 C가 쓰는 계약)

```ts
// packages/cad-core — CadHost
interface LayerDto {
  name: string
  color: number            // ACI. 트루컬러면 7, 실제 값은 colorRgb
  colorRgb?: string        // '#RRGGBB'
  visible: boolean         // isOff의 반대. frozen과 별개다
  frozen: boolean
  locked: boolean
  plottable: boolean
  linetype?: string
  lineweightMm?: number
}

host.layers(): LayerDto[]
host.setLayerVisible(name, visible): boolean      // 없는 레이어면 false
host.setLayersVisible({ [name]: boolean }): void  // 한 번의 리페인트
host.zoomTo(box, marginRatio?)                    // {min,max} 와 {minX..maxY} 둘 다 받는다
host.pick({x, y}, hitRadiusPx?): Handle[]
host.on('selectionChanged', ({handles}) => …)
host.on('renderIdle', ({fileId, durationMs}) => …)
await host.whenRenderIdle()
```

```ts
// apps/web/src/features/viewer/host.ts — 렌더러가 쓰는 얇은 래퍼
await openBytes(fileId, name, bytes)
setLayersVisible(entries); layers(); zoomTo(box, marginRatio?)
onSelection(cb) → unsubscribe; await whenRenderIdle(); screenToWorld(p); pick(p, r?)
```

화면 C의 보기 모드(`docs/contracts/compare-dxf.md` §9)는 이렇게 한 줄이다.

```ts
const MODES = {
  overlay: { __CMP_ADDED: true,  __CMP_REMOVED: true  },
  before:  { __CMP_ADDED: false, __CMP_REMOVED: true  },
  after:   { __CMP_ADDED: true,  __CMP_REMOVED: false },
}
setLayersVisible(MODES[viewMode])
await whenRenderIdle()          // 스크린샷·측정을 할 때만 필요하다
```

번호 배지 클릭은 `onSelection` → 사이드카의 `handle_to_cluster`, 리스트에서 번호 선택은
`clusters[].bbox`(여백 포함)를 그대로 `zoomTo`에 넘긴다. `REV-*`는 항상 표시, `__CMP_LABEL`은
항상 숨김이므로 모드 표에 넣지 않는다.

### 구현 방식과 그렇게 한 이유

- 레이어 표 레코드에 `record.isOff = true`를 **직접 쓰지 않는다.** 렌더러는
  `AcDbDatabase.events.layerModified`가 떠야 다시 그리는데, 그 이벤트는 setter가 아니라 쓰기
  트랜잭션(`AcApLayerService.setLayerOn` → `acapRunServiceEdit`)에서 나온다.
- 그래서 `manager.curDocument.layerService`의 `setLayerOn` / `setLayersVisibility`를 쓴다. 이
  서비스는 레이어를 **이름으로** `AcDbLayerTable.getAt`에서 찾는다. 실도면에서는 레이어와 텍스트
  스타일이 같은 objectId를 쓰는 경우가 있어서(`PLATE`와 `Standard`가 둘 다 id 11), id로 찾으면
  엉뚱한 레코드를 열고 아무 일도 일어나지 않는다.
- **`isFrozen`은 쓰지 않는다.** 1.14.3의 setter가 플래그를 OR로만 넣어서
  (`standardFlags | flag`) 한 번 얼면 절대 못 녹인다. 껐다 켜기가 되는 스위치는 off/on뿐이고,
  §9가 요구하는 것도 그쪽이다.
- 일괄 적용은 끄는 목록·켜는 목록으로 나눠 두 번의 트랜잭션을 돌리지만 **리페인트는 한 번**이다.
  `layerModified`는 뷰를 dirty로만 표시하고 실제 페인트는 다음 애니메이션 프레임에 일어난다.
  키는 정렬해서 처리한다(같은 입력 → 같은 순서, CLAUDE.md 규칙 6).
- `skipCurrentLayer: false`로 부른다. 호출자가 레이어를 명시했는데 CLAYER라는 이유로 조용히
  건너뛰면 `layers()`가 보고하는 상태와 화면이 어긋난다.
- 숨겼다 켜면 그동안 변환하지 않은 엔티티를 뒤늦게 변환한다
  (`AcTrView2d.convertMissingEntitiesOnLayer`, fire-and-forget). 스크린샷이나 픽셀 비교를 할
  거라면 반드시 `whenRenderIdle()`을 기다린다.

## 6. 테스트

- 단위: `packages/cad-core/test/host.test.ts` — 상태 머신, 티어, 스텁 서피스 위의 파사드,
  레이어 가시성(반영·없는 레이어 false·일괄·dispose 후 거부), `zoomTo` 두 가지 박스 모양.
  `packages/cad-core/test/dxfout-postprocess.test.ts` — 후처리 5종 + F06 왕복.
  `packages/cad-core/test/isolation.test.ts` — mlightcad 임포트 경계.
- e2e: `tests/e2e/viewer.spec.ts`가 **실제 Electron·실제 WebGL**로 F06.dxf를 열고, 레이어
  다섯 개를 확인하고, `S-COL`을 껐다 켜면서 `layers()`의 `visible`과 **캔버스 스크린샷 두 장의
  바이트**가 모두 달라지는지 본다. 이어서 핸들 클릭 하이라이트(문서를 열기 **전에** 잡아둔
  `onSelection` 구독에 같은 핸들이 도착하는지까지), 숨김 창 DWG 변환(+ `--xrefs` 메타데이터가
  실제로 돌아오는지), 20회 열기/닫기 힙 증가 <10%.
- `hasTestHooks()`·`waitForStatus()`는 첫 `loadURL`과 경합하면 "Execution context was destroyed"로
  **던진다**(실측 플레이크). 이제 그 오류는 "아직 아님"으로 보고 재시도한다.
- 실도면 `tests/e2e/zz-real.spec.ts`는 `HALO_E2E_REAL=1`일 때만 돈다. `samples/`는 gitignore라
  worktree에도 CI에도 없다.

```bash
pnpm build && pnpm --filter @halo-cad/testing e2e viewer     # 뷰어만
tools/verify.sh --e2e                                        # 전체
HALO_E2E_REAL=1 HALO_E2E_REAL_DIR=<samples>/2026-09-02-실시도서 \
  pnpm --filter @halo-cad/testing e2e zz-real                # 실도면 측정
```

## 7. 알려진 제한

1. **폰트가 없다.** `viewer/fonts/`에 매니페스트만 있고 파일이 없어서 TEXT·MTEXT·ATTRIB의
   글리프가 비어 보인다. 도형·치수·해치는 정상이다. `fontMissing` 이벤트와
   `viewer.warning.fontsMissing` 경고로 올라온다. W3-05가 채운다.
2. **소프트웨어 렌더링을 macOS arm64에서 강제할 수 없다.** `HALO_E2E=1`이면
   `--enable-unsafe-swiftshader`를 켜서 GPU 없는 러너에서도 WebGL이 나오게 하지만,
   *선택*까지 하는 `HALO_E2E_SOFTWARE_GL=1`은 Windows·Linux 전용이다. Electron 44.1.1 /
   macOS arm64에서는 `--use-angle=swiftshader`·`--disable-gpu` 어느 조합도 WebGL 컨텍스트를
   만들지 못한다(실측: "Error creating WebGL context").
3. **DWG 변환은 폴백이다.** R1의 1차 변환기는 배경 ZWCAD(R1-02)이고, 숨김 창 경로는 ZWCAD가
   없을 때를 위한 것이다. e2e는 합성 F06.dwg로만 확인했다 — 실도면 DWG 변환 결과의 합격 판정은
   엔진 교차검증(±0.5%, 감사기 삭제 0)이 하며 아직 Windows 설치본에서 확인하지 않았다.
4. **`visible`은 off/on만이다.** frozen 레이어는 `visible: true, frozen: true`로 보고되고
   화면에는 안 나온다. "실제로 그려지는가"는 `renders(layer)`를 쓴다.
5. **힙은 완전히 0으로 돌아오지 않는다.** F06 20회 열기/닫기 실측 +8.6%(약 89 kB/회)로 예산
   10% 안이지만 0은 아니다. 장시간 세션에서 수백 회 여닫는 사용 방식은 아직 측정하지 않았다.
6. **뷰어 자체 스토어와 셸 스토어가 아직 둘이다.** `features/viewer/viewer-store.ts`(W3-02의
   자급자족 스토어)와 `apps/web/src/state/viewer.ts`(W3-01, zustand)가 공존한다. R1-05가 앱 셸을
   비교 화면으로 갈아끼울 때 하나로 합친다.
