# 화면 A·B, 앱 셸, IPC (R1-05)

R1 렌더러가 도크·탭·명령줄 기반 Halo CAD 셸에서 화면 A(세트 지정) → B(도곽 목록) → C(검토) →
D(출력) 한 줄짜리 흐름으로 바뀌는 지점. 계약은 `docs/contracts/r1.md` §7·§8·§9·§10·§11, 목업은
`docs/plans/dms-local/01-보고용-계획서.html` §3. 구현은 `apps/web/src/app/App.tsx`(셸),
`apps/web/src/features/compare/**`(화면 A·B, 자리표시자 C·D), `apps/web/src/state/compare.ts`
(스토어), `apps/desktop/src/main/ipc.ts`(폴더 선택·클립보드·OS 열기).

## 화면 흐름

```
App.tsx
  AppHeader(제목 + StepIndicator A→B→C→D)
  CompareApp            # state.compare의 screen 필드로만 스위칭(라우터 없음)
    SetScreen           # screen === 'set'
    SheetListScreen      # screen === 'sheets'
    ReviewScreen         # screen === 'review' (자리표시자, R1-08이 교체)
    ExportScreen         # screen === 'export' (자리표시자, R1-10이 교체)
  StatusBar
```

`LeftDock`·`RightDock`·`TabStrip`·`CommandLine`·`MenuBar`·`features/files/**`·`features/xref/**`는
파일을 지우지 않았다 — `App.tsx`가 더는 이들을 렌더하지 않을 뿐이다(각자의 테스트는 그대로 남아
있고 그대로 통과한다).

### 화면 A `SetScreen.tsx`

1. 전/후 폴더 선택(`window.halocad.dialog.pickFolder`) → `state.beforeDir`/`afterDir`.
2. 실행 날짜(`<input type="date">`, 기본값은 렌더러의 오늘 `new Date()`, e2e는 고정값을 훅으로 넘긴다).
3. ZWCAD 상태 칩(`GET /compare/zwcad/status`, 마운트 시 1회 조회).
4. "인입 시작" → `state.startSet()`:
   `POST /compare/sets` → `GET /jobs/{id}` 500ms 폴링(`compare.ingest`) → 요약 새로고침 →
   성공하면 자동으로 `POST /compare/sets/{id}/frames`(`compare.frames`) → 완료하면 화면 B로.
   `frames`가 404(R1-04 미병합)면 토스트 `compare.set.toast.framesNotReady`를 띄우고 화면 A에
   머문다(브리프 "Defaults for ambiguity"와 같은 규칙을 `frames`에도 적용).
5. 요약 카드: 전/후 각각 파일 수·변환 성공·실패·제외, 변환기 불일치 건수, 폰트 누락 목록,
   교차검증 결과(`null`이면 "교차검증 없음"), 실패한 파일 목록(파일명 + 에러 메시지).

### 화면 B `SheetListScreen.tsx`

- 표(`role="table"`): 도면번호·도면명·전·후(표제란 `date_text`)·변경 수·매칭 방법·축척·상태 칩.
- 상태 필터 칩 9개(전체·변경·동일·신규·삭제·짝 없음·미인식·변환기 불일치·대기), 검색(도면번호·
  제목), 정렬(도면번호순/변경 많은 순) — 셋 다 **클라이언트 사이드**(`pairFilters.ts`)다.
  `GET /compare/sets/{id}/pairs`는 새 필터마다 다시 부르지 않고 한 번에 전체 목록(최대 300행,
  페이지네이션 없음)을 받아 두고 화면에서만 걸러 보여준다 — 서버에도 같은 쿼리 파라미터
  (`?status=&q=&sort=`)가 있지만, 이건 순수 표시 로직이라 매 키 입력마다 왕복할 필요가 없다.
- `GET .../pairs`가 404(R1-04 미병합)면 `state.pairsAvailable`이 `false`로 남고, 표 대신
  "준비되지 않았습니다" 패널 + 다시 시도 버튼을 보여준다.
- "짝 없음"(`unpaired`)·"신규"(`added`)·"삭제"(`removed`) 행에 "수동 짝 맞춤" 버튼이 뜬다.
  `ManualPairDialog`는 트리거한 행이 아니라 **전체 목록**에서 전에만 있는 도곽(`before_frame`만
  있고 `after_frame`이 없는 짝)과 후에만 있는 도곽을 나란히 보여준다 — 그래야 `removed` 행과
  `added` 행을 서로 짝지을 수 있다(`fixtures/compare/S14_sheet_added_removed`가 정확히 이
  시나리오). `match_method === 'manual'`인 행은 대신 "짝 해제"(`DELETE /compare/pairs/{id}`)
  버튼을 보여준다.
- 버튼: **비교 실행**(`POST .../run` → `compare.run` 잡 폴링 → 완료 시 목록·요약 새로고침,
  404면 토스트 `compare.sheets.toast.runNotReady`), **도곽 열기**(선택 행 + 그 짝의
  `compare_dxf_path`가 있어야 활성 → `openPair` → 화면 C), **전체 도곽 출력**(비교를 한 번이라도
  성공시켜야 활성 → 화면 D).

## 스토어 (`state/compare.ts`)

```ts
useCompareStore.getState()
// screen, projectDir, beforeDir, afterDir, runDate, compareSetId, summary, files,
// job, pairs, pairsAvailable, filters, selectedPairId, zwcad, hasRunCompare,
// toast, error, busy

// actions
pickBefore() / pickAfter() / setRunDate(date)
loadZwcadStatus()
startSet()            // ingest → (성공하면) startFrames()
startFrames()
refreshSummary()
loadPairs()
setFilters(patch)
selectPair(pairId) / openPair(pairId)
createManualPair(beforeFrameId, afterFrameId) / deletePair(pairId)
startRun(pairIds?)
goto(screen)
dismissToast()
cancelActiveJob()     // 진행 중인 GET /jobs/{id} 폴링을 멈춘다
reset()
```

`toast`는 **번역된 문자열이 아니라 i18n 키**(예: `'compare.set.toast.framesNotReady'`)를
담는다 — 화면이 `t(toast)`로 렌더한다. `error`는 엔진이 준 원문 메시지를 그대로 담는다
(`features/xref/UnresolvedXrefDialog.tsx`와 같은 관례).

`run_date` 기본값은 스토어 모듈이 로드될 때의 `new Date()`(렌더러의 "오늘")이고,
`reset()`을 부르면 다시 그 시점의 오늘 날짜로 되돌아간다. 잡 폴링(`api.pollJob`)은 스토어
액션이 직접 돌리고 취소 핸들을 모듈 스코프 변수에 쥐고 있다(`api/engine.ts`의
`connectionPromise`와 같은 패턴). 화면 컴포넌트는 마운트 해제 시 `cancelActiveJob()`을 부르는
`useEffect` 클린업 하나만 가지면 된다(`SetScreen.tsx` 참고) — 화면을 나가도 폴링이 새지 않는다.

## API 클라이언트 (`features/compare/api.ts`)

`getZwcadStatus`·`createSet`·`getSet`·`getSetFiles`·`startFrames`·`getPairs`·
`createManualPair`·`deletePair`·`startRun`·`getJob`·`pollJob`. 타입(`CompareSetSummary`,
`SheetPair`, `SheetFrame`, ...)은 `docs/contracts/r1.md` §3·§4·§7의 필드 이름을 그대로 쓴
snake_case 손수 미러다 — `@halo-cad/schema`(`packages/schema/gen/ts/compare/*`)를 임포트하지
않는다. 이유는 두 가지: (1) `apps/web/package.json`에 그 패키지를 의존성으로 추가하는 일은
이 태스크의 "Files you own" 밖이고(보고서 "Shared-file patch" 참고), (2) `apps/web/src/api/
types.ts`가 이미 같은 이유로 `apps/desktop`의 타입을 손수 복제하는 관례를 갖고 있다.

`startFrames`/`getPairs`/`startRun`은 404를 **`null`로 흡수**하고 그 외 상태 코드는
`EngineHttpError`로 던진다 — R1-04/R1-06 라우터가 아직 안 붙었을 때의 "준비 중" 처리와,
진짜 오류를 구분하기 위해서다.

## IPC (계약 §8)

| 채널 | preload | e2e 대체 |
|---|---|---|
| `halocad:dialog:pick-folder` | `window.halocad.dialog.pickFolder(title?)` | `HALO_E2E=1`이면 `HALO_E2E_PICK_FOLDERS`(쉼표 구분)를 호출마다 하나씩 FIFO로 소비 |
| `halocad:clipboard:write-text` | `window.halocad.clipboard.writeText(text)` | 그대로 |
| `halocad:shell:open-path` | `window.halocad.shell.openPath(path)` | `HALO_E2E=1`이면 열지 않고 `process.env.HALO_E2E_OPENED_PATHS`(쉼표 구분)에 추가만 |

순수 함수(`apps/desktop/src/main/ipc.ts`): `pickFolder(env, state, showOpenDialog)`,
`recordE2EOpenedPath(env, path)`, `openPath(env, path, shellOpenPath)`. `state: { queue:
string[] | null }`는 `HALO_E2E_PICK_FOLDERS`를 첫 호출에서 한 번만 파싱해 두고 이후 호출마다
`shift()`한다 — 화면 A가 전/후 폴더를 연달아 두 번 고르는 것과 맞춘 설계다.

## 테스트 훅 (`window.__haloTest`, 계약 §10)

`features/compare/CompareApp.tsx`가 마운트 시 한 번 등록한다.

| 이름 | 동작 |
|---|---|
| `compareStartSet({beforeDir, afterDir, runDate})` | 세트 지정 → 인입 잡 → 도곽 잡까지 실행하고 `compare_set_id`로 resolve. 인입·도곽 잡 중 하나라도 실패하거나 토스트로 멈추면 그 사유로 reject한다. |
| `compareGetScreen()` | 현재 `state.screen` |
| `compareGoto(screen)` | `state.goto(screen)` |
| `compareGetSummary()` | `state.summary` |
| `compareGetPairs()` | `state.pairs` |
| `compareRunCompare()` | `state.startRun()`을 완료까지 실행 |

## e2e (`tests/e2e/compare-sheets.spec.ts`)

`fixtures/compare/S13_multi_sheet/{before,after}`(있으면, `plan.dxf` 한 파일에 도곽 2장)를
임시 폴더 두 곳에 복사해 쓴다 — 픽스처 자체 폴더에는 절대 `.halo`를 만들지 않는다(원본 불변
규칙). `HALO_E2E_PICK_FOLDERS=<전 임시폴더>,<후 임시폴더>`를 미리 설정해 두면 화면 A의 "폴더
선택…" 버튼 두 번이 실제 OS 다이얼로그 대신 그 값을 순서대로 받는다.

이 태스크가 병합되는 시점(main)에는 R1-04(`/compare/sets/{id}/frames`, `/pairs`)가 아직
없을 수 있다 — 스펙은 그 경우를 실패로 보지 않는다: 세트 지정 → 인입 잡 완료 → 요약 카드까지는
항상 단언하고, 그다음 `startFrames`가 404면 "준비 중" 토스트가 뜨는 것과 화면이 A에 머무는
것만 확인하고 끝난다. `GET .../pairs`가 실제로 200을 반환할 때만(R1-04가 이미 병합된 상태로
게이트를 돈다면) 도곽 목록 행·필터 칩·`compareGetScreen() === 'sheets'` 단언을 마저 돈다.

## 화면 C 검토 `ReviewScreen.tsx` (R1-08)

왼쪽은 엔진이 만든 비교 DXF 한 장, 오른쪽은 그 사이드카(`clusters.json`)의 클라우드 마크 목록이다.
계약은 `docs/contracts/compare-dxf.md` §9와 `docs/contracts/r1.md` §7·§9·§10. 구현은
`features/compare/ReviewScreen.tsx` + `features/compare/review/**`(ViewModeBar·ClusterList·
ClusterRow·MinorList·testHooks), `features/compare/reviewApi.ts`, `state/review.ts`.

### 데이터 흐름

```
state/compare.ts  selectedPairId          # 화면 B의 "도곽 열기", [ ] 버튼, compareOpenPair 훅
        │  (ReviewScreen의 useEffect 하나)
        ▼
review.loadPair(pairId)
  1. GET  /compare/pairs/{id}/clusters          → sidecar (판정 병합본)
  2. GET  /compare/pairs/{id}/compare-dxf       → If-None-Match: <캐시된 ETag>
        304면 캐시한 바이트를 그대로 쓴다(짝당 1회 다운로드, 최근 4장 보관)
  3. openBytes(`compare:<pairId>`, ...)          # 바뀐 ETag면 이전 문서를 닫고 다시 연다
  4. whenRenderIdle()
  5. setLayersVisible(보기 모드 맵) → whenRenderIdle() → layers()를 읽어 visibleLayers 갱신
```

- 사이드카가 실패하면 목록도 캔버스도 없다(`error`). 뷰어가 실패하면 **목록은 그대로 두고**
  캔버스에만 오류 문구를 띄운다(`renderError`).
- `loadPair`는 짝마다 한 번만 돈다: 화면 마운트 효과와 `compareOpenPair` 훅이 같은 짝을 동시에
  요청하면 진행 중인 약속을 함께 기다린다(같은 도면을 두 번 여는 것은 무해하지 않다).
- 뷰어 모듈(`features/viewer/host.ts` → `@halo-cad/cad-core` → mlightcad)은 **동적 임포트**다.
  그리는 화면은 화면 C뿐이라 앱 셸의 모듈 그래프(와 `app/App.test.tsx`의 jsdom)에 CAD 엔진이
  들어가지 않고, 빌드에서도 mlightcad가 별도 청크로 남는다.
- 선택 동기화는 양방향이다. 캔버스 클릭 → `onSelection(handles)` → 사이드카 `handle_to_cluster`
  → 클러스터 번호(`c1`·`1` 두 형식 모두 처리). 목록 번호 클릭·`J`·`K` → `zoomTo(클러스터 상자,
  1.25)`. 카메라가 맞추는 상자는 `bbox`가 아니라 **클라우드 폴리라인 정점 ∪ 배지 중심**이다
  (bbox만 맞추면 구름과 번호가 화면 밖으로 잘린다). 좌표는 전부 엔진이 준 값이고 렌더러는
  최소·최대만 고른다.
- 판정 왕복은 낙관적이다. 행을 먼저 바꾸고 `PATCH .../clusters/{number}`를 보낸 뒤 서버가 준
  클러스터로 갈아끼우고, 실패하면 원래 행으로 되돌리고 `error`에 엔진 문구를 담는다.
  `counts.approved`·`ignored`는 클러스터 배열에서 다시 세므로 요약 줄이 행과 어긋나지 않는다.
  같은 판정을 다시 누르면 `pending`으로 돌아간다. 문구는 `user_label`에만 쓰고 빈 문자열이면
  `null`(자동 문구가 다시 보인다). Enter 저장, Esc 취소, 포커스가 떠나면 저장.

### 보기 모드

```ts
layerVisibility(mode, sidecar.layer)
// overlay: { __CMP_ADDED: true,  __CMP_REMOVED: true,  __CMP_LABEL: false, REV-…: true }
// before:  { __CMP_ADDED: false, __CMP_REMOVED: true,  … }
// after:   { __CMP_ADDED: true,  __CMP_REMOVED: false, … }
```

레이어 가시성만 바꾸고 도면은 다시 열지 않는다. 적용 뒤 `host.layers()`가 실제로 그리고 있다고
보고한 `__CMP_*`·`REV-*` 레이어를 캔버스 컨테이너의 `data-cmp-visible` 속성으로 내보낸다 —
e2e가 스토어의 의도가 아니라 **호스트의 상태**를 읽을 수 있는 통로다(테스트 훅을 늘리지 않으려고
DOM 속성으로 냈다). 보기 모드는 짝을 바꿔도 유지된다.

**알려진 제한(측정):** 변경이 INSERT면 보기 모드가 그림을 바꾸지 못한다. 뷰어는 가시성을 그려진
엔티티 단위로 따지는데, 블록 정의 안의 도형은 자기 레이어(예: `A-DOOR`)에 있어서 INSERT가 놓인
`__CMP_ADDED`를 꺼도 계속 그려진다. 색도 같은 이유로 빨강·시안이 아니라 원래 레이어 색으로 보인다
(`fixtures/compare/S02_move_door`에서 확인). 선·폴리라인·해치처럼 직접 놓인 엔티티는 정상이다
(`S05_added`의 벽 폴리라인으로 e2e가 확인한다). 해결은 뷰어(cad-core) 또는 비교 DXF 생성 쪽
과제다 — 보고서의 Shared-file patch 참고.

### 접힌 항목

사이드카 `changes[]` 중 `minor: true`인 것들을 `minor_reason`별로 묶어 "접힌 항목 n건" 아래에
펼쳐 보여 준다(사유가 `layer_only+color_only`처럼 여럿이면 각각 번역해 `+`로 잇는다). 캔버스에는
따로 표시하지 않는다 — 접힌 변경은 원래 레이어의 후 엔티티 하나로만 그려진다.

### 키보드

`A` 승인, `X` 무시, `J`·`K` 다음·이전 묶음(끝에서 멈춘다), `[`·`]` 이전·다음 도곽. 입력란에
포커스가 있으면 무시한다. 안내 문구는 패널 아래 `compare.review.shortcuts`.

### 스토어 (`state/review.ts`)

```ts
useReviewStore.getState()
// pairId, sidecar, viewMode, selectedCluster, showMinor, loading, error, renderError, visibleLayers
loadPair(pairId) / select(number|null) / selectByHandles(handles) / selectStep(±1)
decide(number, decision) / setLabel(number, text) / setNote(number, text)
setViewMode(mode) / toggleMinor() / reset()
// 순수 함수: layerVisibility, clusterViewBox, clusterOfHandles, visibleCompareLayers
// 상수: REVIEW_CANVAS_ID('viewer-root'), CLUSTER_ZOOM_MARGIN(1.25)
```

### 테스트 훅

`features/compare/review/testHooks.ts`가 **모듈 스코프에서** 등록한다(화면 B에 있는 동안
`compareOpenPair`를 부르므로 마운트 효과로는 늦다).

| 이름 | 동작 |
|---|---|
| `compareOpenPair(pairId)` | `openPair` → `#viewer-root`가 붙기를 기다림 → `loadPair` 완료(렌더 끝)까지 |
| `compareGetClusters()` | 현재 사이드카 |
| `compareDecide(number, decision)` | `PATCH` 왕복까지. 같은 판정을 다시 주면 `pending` |

### e2e (`tests/e2e/compare-review.spec.ts`)

앱 하나로 여섯 개를 이어서 돈다(모두 임시 폴더 사본, 픽스처는 건드리지 않는다).
S02_move_door 비교 → 검토 진입(클러스터 1, `REV-20260904`) → 휠로 카메라를 멀리 보낸 뒤 번호
클릭으로 되돌아오는지(캔버스 픽셀 비교) → 승인 후 엔진에서 다시 읽어 `approved` 확인 → 전·후·
겹쳐 보기의 `data-cmp-visible` → S05_added로 보기 모드가 실제로 다시 그리는지 → S13_multi_sheet로
"다음 도곽"이 화면을 떠나지 않고 다음 시트를 여는지.

### 화면을 떠났다 오면 뷰어를 다시 만든다

`CadHost`는 처음 마운트된 `#viewer-root`를 잡고 있는 모듈 싱글턴인데, 화면 C는 목록으로 나갈
때마다 언마운트된다. 다시 들어오면 React가 **새 빈 컨테이너**를 주고 호스트는 버려진 컨테이너에
계속 그린다 — 레이어 표는 멀쩡한데 캔버스만 새까맣다(e2e에서 두 번째 시트로 재현). 그래서
`loadPair`는 컨테이너가 비어 있는데 호스트가 살아 있으면 `disposeCadHost()`로 버리고 새로 만든다.
바이트는 캐시에 남아 있어 다시 내려받지는 않는다. `cad-core`에 `attach(container)`가 생기면
이 자리를 대신할 수 있다.

## 화면 D 출력 `ExportScreen.tsx` (R1-10)

화면 C에서 승인·무시를 끝내고 화면 B의 "전체 도곽 출력…"으로 넘어오면 보는 화면. 계약은
`docs/contracts/r1.md` §7(export 엔드포인트)·§9·§10, 산출물 규칙은 `docs/dev/compare-export.md`
(R1-09). 구현은 `features/compare/ExportScreen.tsx` + `exportApi.ts`, `state/export.ts`.

### 데이터 흐름

```
state/compare.ts  compareSetId, summary, pairs, zwcad     # 화면 A·B가 이미 갖고 있다
        │
        ▼
ExportScreen 마운트
  1. summary.run_date → state/export.ts의 runDate 초기값 (compareSetId가 바뀔 때만 다시 설정)
  2. cluster_count > 0 && compare_dxf_path가 있는 pairs마다 GET .../clusters (화면 C와 같은
     호출)를 병렬로 불러 counts.approved/ignored를 합산 → "승인 n건 · 무시 n건 · 대상 도곽 n장"
     (Run이 아직 없으니 승인·무시 집계를 보여줄 다른 출처가 없다 -- 이 사전 요약만 유일하게
     사이드카를 다시 읽는다. "출력 실행" 뒤의 결과 표는 전부 Run 필드만 쓴다)

"출력 실행" 클릭
  1. state/export.ts::runExport({compareSetId, runDate})
  2. POST /compare/sets/{id}/export {run_date, scope:"all", method:"auto"} → 202 {job_id, run_id}
  3. GET /jobs/{id} 500ms 폴링(features/compare/api.ts의 pollJob 재사용, kind `compare.export`,
     stage `markup`/`dwg`) → JobProgress 컴포넌트가 그대로 그린다(단계 이름 매핑이 없으면
     원문 stage를 그대로 보여준다 -- R1-05의 JobProgress.tsx는 이 태스크 소유가 아니라 손대지
     않았다. 보고서 "Shared-file patch" 참고)
  4. 잡 완료 → GET /compare/runs/{run_id} → Run을 스토어에 저장 → 결과 표 렌더
```

### 결과 표는 `Run` 필드만

브리프 Constraints("렌더러가 파일을 읽지 않는다")를 결과 표에도 그대로 적용했다: 도면번호·
파일·형식·라이터는 `Run.files[]`를 그대로 옮기고, "경고" 열도 새 데이터를 불러오지 않고
`writer === 'dxf-only'`일 때만 (ZWCAD 없음 또는 실패로 DXF로 떨어진 경우, `docs/dev/
compare-export.md`의 "DWG 저장 경로 선택" 표) 경고 문구를 파생시킨다. `compare_set.stats.
export.warnings`(짝 단위가 아닌 실행 전체 경고)는 Run 스키마에 없는 필드라 화면 D에는
나오지 않는다 — 필요하면 스키마에 필드를 추가하는 별도 태스크가 맞다(보고서 "Shared-file
patch").

### 스토어 (`state/export.ts`)

```ts
useExportStore.getState()
// runDate, run, exportJob, busy, error, toast
runExport({ compareSetId, runDate })   // POST export → 잡 폴링 → GET run
copyTsv()                              // GET .../tsv → clipboard.writeText, 2초 토스트
openOutput()                           // shell.openPath(run.output_dir)
cancelActiveJob()                      // 화면을 떠날 때 잡 폴링 정리
reset()
```

`state/compare.ts`(어느 세트인지)와 `state/review.ts`(어느 짝을 보고 있는지)가 그렇듯,
이 스토어는 "이 세트가 지금까지 낸 출력 하나"만 안다 — 여러 짝을 오가는 화면 C와 달리 화면 D는
세트당 상태가 하나뿐이라 `pairId` 같은 키가 필요 없다.

### API 클라이언트 (`features/compare/exportApi.ts`)

`startExport`·`getRun`·`getRunTsv`. 타입(`Run`, `RunOutputFile`)은 다른 `*Api.ts`들과 같은
이유로 `packages/schema/gen/ts/compare/run.d.ts`의 손수 미러다. `startExport`는 R1-04/R1-06의
API처럼 404를 흡수하지 않는다 — 화면 D에 도달했다는 것 자체가 R1-09의 export 라우터가 이미
병합돼 있다는 뜻이라(브리프 Wave "D5, R1-08·R1-09 병합 후 시작"), 여기서 404는 진짜 오류다.

### 테스트 훅

`ExportScreen.tsx` 모듈 스코프에서 등록한다(화면 C의 `registerReviewTestHooks()`와 같은 이유 --
`CompareApp.tsx`가 이 파일을 정적으로 임포트하므로 화면 D가 마운트되기 전에도 이미 등록돼 있다).

| 이름 | 동작 |
|---|---|
| `compareRunExport({runDate})` | `state/export.ts::runExport`를 완료까지 실행하고 끝난 `Run`으로 resolve. `compareSetId`는 `state/compare.ts`에서 직접 읽는다 |
| `compareGetLastRun()` | 스토어의 `run` 필드를 그대로 반환(부작용 없음 -- 다시 출력하지 않는다) |

### e2e (`tests/e2e/compare.spec.ts`)

Seed AC4의 수직 슬라이스 전체(세트 지정 → 도곽 목록 → 검토 → 전체 도곽 출력)를 한 스펙으로
잇는다. 자세한 내용은 `docs/dev/e2e.md`의 "compare 수직 슬라이스" 절 참고. 화면 D 자체는 "출력
실행" 버튼을 실제로 눌러(하네스 훅이 아니라) 잡 완료까지 기다린 뒤 결과 표·"폴더 열기"·"TSV
복사"를 확인하고, `compareGetLastRun()`은 부작용 없이 구조화된 `Run` 값을 읽어오는 용도로만
쓴다(재출력을 유발하는 `compareRunExport` 훅을 같은 스펙에서 또 부르면 `출력/2026-09-04-2`가
새로 생겨 폴더 이름 단언이 깨진다 -- 두 경로는 어차피 같은 `runExport` 액션을 부른다).

## Windows 확인이 필요한 부분

없음 — 이 태스크의 기능은 macOS 개발 환경에서도 `tools/verify.sh --e2e`로 전부 검증된다
(ZWCAD 자체는 R1-02가 검증). ZWCAD 칩은 macOS에서 항상 "자체 변환기 · Windows 아님"으로
보이는 것이 정상이다. 화면 D에서 실제 `.dwg`가 나오는지, 라이터가 `zwcad-com`으로 찍히는지는
`docs/dev/compare-export.md`의 "Windows 확인 절차"가 다룬다(R1-09 소유 문서).
