# Wave 2 통합 계약 (Fable 고정, 2026-09-02)

Wave 2 태스크가 공유하는 이름과 형식. 여기 적힌 것을 바꾸려면 Fable에게 "Shared-file patch"로 제안한다.

## 사이드카 (W2-01 ↔ engine)
- 실행: 개발 `uv run halo-engine serve --data-dir <userData>/engine` (cwd `engine/`, uv는 `$HOME/.local/bin/uv` 폴백), 프로덕션 `<process.resourcesPath>/engine/halo-engine serve --data-dir <userData>/engine`.
- env: `HALO_ENGINE_TOKEN`(32바이트 hex), `HALO_ENGINE_PARENT_PID`, `PYTHONUTF8=1`. argv에 토큰 금지.
- READY: stdout 첫 줄 `{"event":"ready","port":N,"pid":P,"version":"x.y.z"}`. 30초 내 미수신 → 실패.
- health: `GET http://127.0.0.1:<port>/api/v1/system/health` (무토큰). shutdown: `POST /api/v1/system/shutdown` (Bearer).
- 부착 모드: `HALO_ENGINE_URL` + `HALO_ENGINE_TOKEN`이 설정되면 spawn 생략.
- 상태 머신: `starting → ready → (crashed → restarting)×3 → failed`. 재시작 백오프 1s, 3s, 9s.

## IPC 채널 (main ↔ preload ↔ renderer)
- `halocad:engine:get-connection` (invoke) → `{ baseUrl: string, token: string }`. 렌더러 세션당 1회 호출.
- `halocad:engine:status` (main → renderer send) payload `{ state: 'starting'|'ready'|'restarting'|'failed', version?: string, port?: number, attempt?: number, message?: string }`.
- `halocad:app:info` (invoke) → `{ version, platform }` (W1-01 기존 API 유지).
- preload 전역: `window.halocad = { app: { getVersion(), platform }, engine: { getConnection(): Promise<...>, onStatus(cb): () => void } }`.

## 렌더러 엔진 클라이언트 (apps/web/src/api/)
- `engine.ts`: `getEngine(): Promise<{ baseUrl, token }>`, `engineFetch(path, init)`가 `Authorization: Bearer` 자동 부착. 아직 openapi-typescript는 쓰지 않음(W8-05).
- i18n 키: `status.engine.disconnected`, `status.engine.starting`, `status.engine.ready` (`엔진: 연결됨 v{{version}}`), `status.engine.restarting`, `status.engine.failed`.

## 테스트 훅 (W2-07 ↔ apps)
- env `HALO_E2E=1`이면 렌더러가 `window.__haloTest = { getStatus(): string }`를 노출한다. 그 외에는 정의하지 않는다.
- W1-01의 `HALO_E2E_SMOKE` / `HALO_E2E_SCREENSHOT`(main 프로세스 스모크)는 유지.

## 패키징 (W2-08)
- 산출 경로: `engine/dist/halo-engine/`(PyInstaller onedir) → electron-builder `extraResources`로 `<resources>/engine/`.
- `apps/web/dist` → `<resources>/web/`. `halocad://app` 핸들러는 `app.isPackaged ? join(process.resourcesPath,'web') : join(appPath,'../web/dist')`.
- 아티팩트 이름: `Halo CAD-<version>-arm64.dmg`, `Halo CAD-<version>-arm64-mac.zip`.

## CI (W2-09)
- 워크플로 `ci.yml`: 매트릭스 `macos-14`, `windows-latest`. 필수 잡: `ts`(pnpm lint/typecheck/test), `engine`(uv sync/ruff/mypy/pytest), `verify`(bash tools/verify.sh, mac만). 패키징 잡은 W2-08이 붙인다.
- 러너 도구: `pnpm/action-setup`은 쓰지 않고 corepack 사용(`packageManager` 필드), `astral-sh/setup-uv`.
