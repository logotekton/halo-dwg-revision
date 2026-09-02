# Electron e2e (Playwright)

`packages/testing`(`@halo-cad/testing`)가 빌드된 Electron 앱(`apps/desktop/out/main` +
`apps/web/dist`)을 Playwright의 `_electron.launch()`로 직접 띄워 확인하는 e2e 골격이다.
Chromium 브라우저를 따로 다운로드하지 않는다 — Electron 자신이 테스트 대상이자 구동
엔진이다. 테스트 스펙은 `tests/e2e/**`(저장소 루트)에 둔다. 계약은
`docs/contracts/wave-2.md` "테스트 훅" 절, 사이드카 배경은 `docs/dev/engine-sidecar.md`.

## 실행 방법

```bash
pnpm build                                   # apps/desktop/out/**, apps/web/dist 생성
pnpm --filter @halo-cad/testing e2e          # headless, list + html 리포터
pnpm --filter @halo-cad/testing e2e:headed   # 창을 띄워서 눈으로 확인
tools/verify.sh --e2e                        # pnpm -r --if-present run e2e 를 호출
```

빌드 산출물이 없으면(`pnpm build`를 안 돌렸으면) `launchHalo()`가 누락된 경로를 나열하는
한글 에러로 즉시 실패한다(테스트 자체가 타임아웃까지 기다리지 않는다).

HTML 리포터는 `playwright-report/`(저장소 루트)에 쓰지만 실행 후 자동으로 열지 않는다
(`open: 'never'`). 보고 싶으면 `npx playwright show-report ../../playwright-report`를
`packages/testing`에서 실행하거나 그 디렉터리를 직접 브라우저로 연다.

## 구성

```
packages/testing/
  package.json          # @halo-cad/testing, "e2e"/"e2e:headed" 스크립트
  playwright.config.ts  # testDir=tests/e2e, outputDir=test-results/ (둘 다 저장소 루트 기준)
  src/electron.ts        # launchHalo(), hasTestHooks(), waitForStatus()
  src/fixtures.ts         # test/expect: launch+close 자동화, 실패 시 스크린샷+콘솔로그 첨부
tests/e2e/
  smoke.spec.ts          # 창 제목 · 헤더 · 상태바 · (있으면) 엔진 ready 단언
```

`playwright.config.ts`는 `packages/testing`이 아니라 저장소 루트 기준 절대경로로
`testDir`/`outputDir`를 계산한다(`__dirname` 기반) — `pnpm --filter @halo-cad/testing e2e`든
`tools/verify.sh --e2e`(루트에서 `pnpm -r --if-present run e2e`)든 실행 위치(cwd)에
관계없이 항상 같은 곳(`<repo>/tests/e2e`, `<repo>/test-results`)을 본다.

## 새 테스트 추가하기

`tests/e2e/`에 `*.spec.ts` 파일을 추가한다. `packages/testing/src/fixtures`의 `test`/`expect`를
쓰면 앱 launch/close와 실패 시 아티팩트 첨부가 자동으로 따라온다.

```ts
import { expect, test } from '../../packages/testing/src/fixtures'

test('설명', async ({ window }) => {
  // window: 첫 BrowserWindow의 Playwright Page
  await expect(window.locator('header')).toContainText('...')
})
```

엔진 상태(`window.__haloTest`)가 필요하면 `packages/testing/src/electron`의
`hasTestHooks(window)` / `waitForStatus(window, state, timeoutMs)`를 쓴다. `smoke.spec.ts`가
그 패턴을 보여준다 — 훅이 없으면(W2-01이 아직 병합되지 않았거나 `HALO_E2E`가 꺼진 경우)
`test.skip(true, 사유)`로 건너뛰고 실패시키지 않는다.

## 테스트 훅 규약 (`window.__haloTest`)

`docs/contracts/wave-2.md` "테스트 훅": main 프로세스가 `HALO_E2E=1`로 시작되면(그리고
그 값이 preload를 거쳐 렌더러에 `window.__HALO_E2E_ENABLED__ === true`로 전달되면)
`apps/web/src/test-hooks.ts`가 `window.__haloTest = { getStatus(): string }`를 등록한다.
`getStatus()`는 지역화된 상태바 문구가 아니라 엔진 상태 머신의 원시 값(`'starting' |
'ready' | 'restarting' | 'failed'`, 또는 아직 아무 상태도 못 받았으면 `'disconnected'`)을
반환한다 — 자동화 단언이 로캘에 흔들리지 않게 하기 위함이다. `launchHalo()`가 항상
`HALO_E2E: '1'`을 자식 프로세스 env에 넣으므로, `apps/web/src/test-hooks.ts`가
바뀌지 않는 한 이 harness로 뜬 앱에서는 훅이 항상 켜져 있다.

`hasTestHooks()`는 한 번만 확인하지 않고 최대 5초 폴링한다 — `firstWindow()`는 페이지의
CDP 타깃이 생기자마자 resolve되는데, 이는 React가 `StatusBar`(훅을 등록하는 컴포넌트)를
마운트하기 *전*일 수 있다. 즉시 한 번만 확인하면 W2-01이 병합돼 있어도 마운트 타이밍과
경합해 잘못 스킵될 수 있다.

## 아티팩트 (실패 시)

- **스크린샷만, 비디오는 없음** (`playwright.config.ts`의 `use: { screenshot:
  'only-on-failure', video: 'off', trace: 'off' }`).
- `packages/testing/src/fixtures.ts`의 `window` 픽스처가 테스트 종료 후 상태를 확인해,
  실패(또는 타임아웃)면 **직접 한 번 더** `window.screenshot()`을 찍어
  `test-results/<test-name>/failure.png`로 저장하고 리포트에도 첨부한다 — Playwright
  내장 자동 캡처와는 별도의, 확실히 동작하는 경로다. 같은 타이밍에 렌더러가 남긴 콘솔
  메시지가 있으면 `console-log.txt`로 함께 첨부한다.
- 모두 `test-results/`(저장소 루트, `.gitignore`에 이미 포함) 아래에 테스트별 하위
  디렉터리로 쌓인다. 커밋하지 않는다.
- 검증 방법: 아무 단언의 기대값을 의도적으로 틀리게 바꾸고 `pnpm --filter
  @halo-cad/testing e2e`를 돌리면 `test-results/.../failure.png`(+ 내장
  `test-failed-1.png`)가 생기는 것을 확인할 수 있다. 이 태스크의 완료 조건 중 하나로
  실제로 1회 실행해 확인한 뒤 원래 값으로 복원했다(보고서 "Verification" 참고).

## 타임아웃

- 테스트 전체: 60초(`playwright.config.ts`의 `timeout`).
- 앱 기동 대기: 30초(`launchHalo()`의 `launchTimeoutMs` 기본값 — `_electron.launch()`와
  `firstWindow()` 양쪽에 적용).
- 엔진 ready 대기: `waitForStatus()`의 `timeoutMs` 인자(스모크 테스트는 30초로 호출).

## 알려진 함정: Electron 실행 인자는 파일이 아니라 디렉터리로

`launchHalo()`는 `_electron.launch({ args: [...] })`에 `apps/desktop/out/main/index.js`
파일 경로가 아니라 **`apps/desktop` 패키지 디렉터리**를 넘긴다(`package.json`의 `"main":
"out/main/index.js"`를 Electron이 따라간다). 이유는 스타일이 아니라 실측된 버그
때문이다 — Electron을 파일 경로로 직접 실행하면(`electron
/path/to/out/main/index.js`) `app.getAppPath()`가 그 파일이 있는 디렉터리
(`.../out/main`)로 잡힌다. `electron .`처럼 `package.json`이 있는 디렉터리로 실행할 때
잡히는 패키지 루트(`.../apps/desktop`)와 다르다. `apps/desktop/src/main/protocol.ts`의
`resolveWebDistDir()`와 `index.ts`의 `engineDevDir()`가 둘 다 `app.getAppPath()`에서
상대경로로 실제 리소스 위치를 계산하므로, 틀린 베이스 경로를 쓰면 `halocad://app/*`가
404가 나고(빈 `document.title`) 엔진 스폰의 `cwd`도 존재하지 않는 경로가 된다.
후자는 스폰을 그냥 실패시키는 데 그치지 않고 — 실측 확인함 — Electron의 전체 프로세스가
멎어버려 `_electron.launch()`가 의존하는 `--remote-debugging-port` CDP 엔드포인트조차
응답하지 않게 된다(그래서 원인을 가리키는 단서 없이 그냥 "launch timeout"으로만
보인다). 자세한 재현 과정과 `apps/desktop` 쪽 근본 수정 제안은 이 태스크(W2-07) 보고서의
"Shared-file patch"를 참고한다 — `apps/desktop/**`는 이 태스크의 소유 범위 밖이라 여기서는
`launchHalo()` 쪽에서 우회했다.

## 문제 해결

- **"Halo CAD 빌드 산출물을 찾을 수 없습니다"**: `pnpm build`를 먼저 실행한다
  (`apps/desktop/out/main/index.js`, `apps/web/dist`가 있어야 한다).
- **`Error: Electron uninstall` 계열 오류**: `docs/dev/setup.md`의 "문제 해결: 'Error:
  Electron uninstall'" 절을 따른다 — `packages/testing`도 `electron`을
  devDependency로 갖고 있으므로(아래 "Decisions" 참고) 같은 증상이 날 수 있다.
- **엔진 ready 단언이 항상 스킵됨**: `window.__haloTest`가 없다는 뜻이다. W2-01의
  `apps/web/src/test-hooks.ts` / `StatusBar.tsx` 배선이 현재 브랜치에 없거나,
  `HALO_E2E` 환경변수가 자식 프로세스까지 전달되지 않았는지 확인한다(`launchHalo()`가
  항상 설정하므로 이 harness를 쓰는 한 정상적으로는 발생하지 않는다).
- **엔진 ready 단언이 30초 안에 실패함**: `uv`가 PATH에 없거나(`docs/dev/setup.md`
  요구사항), 처음 실행이라 `uv run`이 가상환경을 새로 만들고 있어 느릴 수 있다(첫
  실행은 몇 초~수십 초가 걸릴 수 있음 — 두 번째 실행부터는 캐시돼 빠르다).
