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

## Windows 확인이 필요한 부분

없음 — 이 태스크의 기능은 macOS 개발 환경에서도 `tools/verify.sh --e2e`로 전부 검증된다
(ZWCAD 자체는 R1-02가 검증). ZWCAD 칩은 macOS에서 항상 "자체 변환기 · Windows 아님"으로
보이는 것이 정상이다.
