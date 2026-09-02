# 개발 환경 설정

Halo CAD 데스크톱 앱(`apps/desktop`)과 웹 렌더러(`apps/web`)를 로컬에서 설치·실행·디버그하는 방법이다. macOS 기준(Windows 검증은 W2-09의 CI에서).

## 요구사항

- Node 24 (`.nvmrc` 참고)
- pnpm 10 (corepack): `corepack enable && corepack prepare pnpm@10.34.5 --activate`
- 관리자 권한 설치(Homebrew 등) 불필요. `pnpm install`만으로 충분하다.

## 설치

```bash
pnpm install --frozen-lockfile
```

## 개발 실행

```bash
pnpm dev
```

내부적으로 `apps/desktop`의 `dev` 스크립트(`apps/desktop/scripts/dev.mjs`)가 두 프로세스를 순서대로 띄운다.

1. `apps/web`의 Vite dev 서버를 `http://127.0.0.1:5173`에 고정 포트(`--strictPort`)로 실행.
2. 그 포트가 응답하면 `electron-vite dev`(main + preload 빌드·watch)를 `HALO_WEB_DEV_SERVER_URL=http://127.0.0.1:5173` 환경변수로 실행. electron-vite가 빌드 완료 후 Electron을 자동 실행하고, main 프로세스(`apps/desktop/src/main/window.ts`)가 그 URL을 `BrowserWindow.loadURL()`로 로드한다.

`apps/desktop`은 electron-vite로 **main + preload만** 빌드한다(renderer 설정 없음). `apps/web`은 완전히 독립된 Vite 앱이며, `halocad://app` 커스텀 프로토콜(운영) 또는 위 dev 서버(개발)로만 로드된다 — electron-vite의 렌더러 파이프라인을 쓰지 않는다.

창 제목은 "Halo CAD"로 고정된다(`apps/desktop/src/main/strings.ko.json`). 페이지의 `<title>`이 바뀌어도 `page-title-updated` 핸들러가 되돌린다.

## 빌드 + 운영 모드 실행

```bash
pnpm build
pnpm --filter @halo-cad/desktop start
```

`pnpm build`는 `apps/web/dist`(Vite 빌드)와 `apps/desktop/out/{main,preload}`(electron-vite 빌드)를 만든다. `start`는 `electron .`으로 빌드 결과를 실행하며, `HALO_WEB_DEV_SERVER_URL`이 없으므로 main 프로세스가 `halocad://app/index.html`을 로드한다. 이 커스텀 스킴은 `apps/desktop/src/main/index.ts`에서 `protocol.handle()`로 등록되고, `apps/web/dist`를 앱 디렉터리 기준 상대 경로(`app.getAppPath()/../web/dist`)로 서빙한다. 패키징(electron-builder, 리소스 배치)은 W2-08에서 다룬다.

## 개발자 도구 / 디버그

- 개발 모드에서는 일반 Chromium DevTools를 그대로 쓸 수 있다(렌더러가 `http://127.0.0.1:5173`이므로 브라우저에서 직접 열어 확인해도 된다).
- electron-vite는 `REMOTE_DEBUGGING_PORT`, `V8_INSPECTOR_PORT` 환경변수를 지원한다. 예: `REMOTE_DEBUGGING_PORT=9222 pnpm dev` 후 `chrome://inspect`로 렌더러에 CDP로 붙을 수 있다.
- main 프로세스 로그는 `pnpm dev`를 실행한 터미널에 그대로 출력된다(`stdio: 'inherit'`).

### 자동 스모크 체크(창 제목 · 스크린샷)

사람이 지켜보지 않는 셸에서 "Electron 창이 실제로 뜨고 제목이 맞는가"를 확인하기 위한 테스트 전용 훅이 main 프로세스에 있다(`apps/desktop/src/main/window.ts`). 평소에는 비활성 상태이며, 다음 두 환경변수로만 켜진다.

```bash
HALO_E2E_SMOKE=1 \
HALO_E2E_SCREENSHOT=/tmp/halocad-smoke.png \
pnpm --filter @halo-cad/desktop dev
```

렌더러 로드가 끝나면(`did-finish-load`) stdout에 `E2E_WINDOW_TITLE:<제목>`을 출력하고, `HALO_E2E_SCREENSHOT` 경로가 있으면 `webContents.capturePage()`로 PNG를 저장한 뒤(`E2E_SCREENSHOT_WRITTEN:<경로>`) 앱을 종료한다. 15초 안에 로드가 끝나지 않아도 안전장치로 같은 절차를 실행하고 종료한다. W2-07의 Playwright e2e 골격이 같은 패턴을 재사용할 수 있다.

## 문제 해결

- **포트 5173이 이미 사용 중**: `HALO_WEB_PORT=5174 pnpm dev`로 다른 포트를 지정한다(main 프로세스는 `HALO_WEB_DEV_SERVER_URL`을 그대로 신뢰하므로 두 값이 같이 바뀐다).
- **`pnpm dev`가 멈춘 것처럼 보임**: `apps/web` dev 서버가 30초 안에 응답하지 않으면 `scripts/dev.mjs`가 타임아웃 에러를 내고 종료한다. `pnpm --filter @halo-cad/web dev`만 따로 실행해 Vite 자체 에러를 확인한다.
- **CSP 위반으로 렌더러가 깨짐**: `apps/web/index.html`의 `Content-Security-Policy` 메타 태그를 확인한다. 새 외부 리소스가 필요하면 태그를 수정하고 이유를 커밋 메시지에 남긴다(임의로 `unsafe-eval` 등을 추가하지 않는다).

## 문제 해결: "Error: Electron uninstall"

pnpm 10은 패키지의 설치 후 스크립트를 기본 차단한다. `pnpm-workspace.yaml`의 `allowBuilds`에 `electron`과 `esbuild`가 허용돼 있지만, 차단된 상태로 한 번 설치된 뒤에는 `pnpm install`이 스크립트를 다시 실행하지 않는다. 이때는 아래 중 하나를 실행한다.

```bash
pnpm -r rebuild electron
# 그래도 apps/desktop/node_modules/electron/path.txt 가 없으면
node node_modules/.pnpm/electron@*/node_modules/electron/install.js
```
