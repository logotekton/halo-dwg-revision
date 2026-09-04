# CI (GitHub Actions)

`.github/workflows/ci.yml`이 `push`, `pull_request`, `workflow_dispatch`에서 매트릭스 `macos-14` / `windows-latest`로 실행된다. 패키징 잡(electron-builder)은 W2-08 이후 별도 태스크가 이 파일에 추가한다.

## 잡 구성

| 잡 | OS | 내용 | 필수 여부 |
|---|---|---|---|
| `ts` | macos-14, windows-latest | `corepack prepare --activate` → `pnpm install --frozen-lockfile` → `pnpm -r lint` → `pnpm -r typecheck` → `pnpm -r test` | 양 OS 필수 |
| `engine` | macos-14, windows-latest | `astral-sh/setup-uv` → `uv python install 3.12` → (`cd engine`) `uv sync --frozen` → `uv run ruff check .` → `uv run ruff format --check .` → `uv run mypy` → `uv run pytest -q` | 양 OS 필수 |
| `verify` | macos-14, windows-latest | `bash tools/verify.sh` (금지어·GPL 경계·높이 규칙 grep 가드 + TS/엔진 전체) | **mac만 필수**. Windows 레그는 `continue-on-error: true` (Git Bash로 시도, 실패해도 워크플로 전체를 빨갛게 만들지 않음) |

세 잡은 서로 독립(`needs` 없음)이라 병렬로 돈다. 각 잡은 `fail-fast: false`라 한쪽 OS가 실패해도 다른 OS 결과를 계속 볼 수 있다.

`ts`, `verify`에는 Electron 창을 여는 테스트를 넣지 않는다 — `apps/desktop`의 `test` 스크립트는 vitest 단위 테스트만 실행한다(`HALO_E2E_SMOKE` 스모크는 `pnpm dev` 경로에서만 수동/별도로 켠다). Playwright e2e(W2-07)는 `--e2e` 플래그가 있어야 도는데 CI는 플래그 없이 `tools/verify.sh`를 실행하므로 여기 포함되지 않는다.

## 도구 선택 근거

- **corepack, `pnpm/action-setup` 아님**: `docs/contracts/wave-2.md` CI 절 고정. `actions/setup-node@v7`로 Node를 올린 뒤(`.nvmrc` = `24`) `corepack enable && corepack prepare --activate`가 루트 `package.json`의 `"packageManager": "pnpm@10.34.5"`를 그대로 읽어 활성화한다.
- **`astral-sh/setup-uv@v10`**: uv 설치 + `enable-cache: true`(캐시 키는 `uv.lock`/`engine/pyproject.toml` 해시). 이어서 `uv python install 3.12`로 `engine/pyproject.toml`의 `requires-python = ">=3.12,<3.13"`을 만족하는 인터프리터를 관리형으로 설치한다.
- **pnpm 스토어 캐시**: `pnpm store path --silent`로 얻은 경로를 `actions/cache@v6`에 넘기고, 키는 `${{ runner.os }}-pnpm-store-${{ hashFiles('pnpm-lock.yaml') }}`.
- **동시성**: `concurrency: { group: ${{ github.workflow }}-${{ github.ref }}, cancel-in-progress: true }` — 같은 브랜치에 새 push가 오면 이전 실행을 취소한다.
- **`git config --global core.autocrlf false`**: 모든 잡의 첫 스텝. `windows-latest` 러너는 기본적으로 `core.autocrlf=true`라 체크아웃 시 LF를 CRLF로 바꾼다. `tools/verify.sh`처럼 셔뱅으로 실행되는 bash 스크립트가 CRLF로 바뀌면 `$'\r': command not found`류 오류가 난다 — 체크아웃 전에 꺼서 원본 LF를 그대로 받는다.

## 로컬 재현

```bash
# TS
corepack enable && corepack prepare --activate
pnpm install --frozen-lockfile
pnpm -r lint
pnpm -r typecheck
pnpm -r test

# 엔진 (engine/에 uv.lock이 없다 — 루트 uv.lock의 워크스페이스 멤버라서 uv가 알아서 찾는다)
# 주의: 엔진 pytest를 tools/verify.sh 밖에서 단독으로 돌릴 때도 위 TS 단계의
# `pnpm install --frozen-lockfile`과 `pnpm --filter @halo-cad/schema build`가 먼저 필요하다.
# 엔진 테스트 일부(acad-ts 폴백·DWG XREF·live round trip·compare 인입 폴백)가
# packages/acad-bridge/bin/acad-bridge.mjs를 node로 실행하고, 그 CLI는
# @node-projects/acad-ts와 @halo-cad/schema/dist를 런타임에 찾는다(없으면
# ERR_MODULE_NOT_FOUND로 FAIL). CI의 engine 잡도 같은 이유로 두 단계를 먼저 한다.
cd engine
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q

# verify (둘 다 필요)
bash tools/verify.sh
```

`engine/pyproject.toml`은 루트 `pyproject.toml`의 uv 워크스페이스(`[tool.uv.workspace] members = ["engine"]`) 멤버라서 잠금파일은 루트 `uv.lock` 하나뿐이다. `engine/uv.lock`은 존재하지 않으므로 `tools/verify.sh`도 `cd engine`한 뒤 그 파일 유무만 보고 `uv sync`를 건너뛰지만, 뒤이은 `uv run ...` 호출이 워크스페이스를 인식해 필요하면 알아서 동기화한다(이 문서 작성 중 `.venv` 삭제 후 콜드 스타트로 직접 확인함).

## Windows에서 알려진 차이 / 위험 지점

실제 실행은 Actions 탭에서만 확인 가능(이 머신엔 `gh` 없음, 비공개 저장소). 아래는 워크플로 작성 시점에 분석한 위험 지점과 대응이다.

1. **줄바꿈(CRLF)**: 위에서 설명한 `core.autocrlf false`로 대응. 이게 없으면 `verify` 잡의 `bash tools/verify.sh` 스텝이 스크립트 자체의 셔뱅 파싱에서 깨질 수 있다.
2. **`grep` 옵션**: `tools/verify.sh`는 GNU 전용에 가까운 `-rniE`, `--include`, `--exclude-dir`을 쓴다. `windows-latest`의 Git Bash는 MSYS2 GNU grep을 번들하므로(리눅스와 동일 계열) 이 옵션들을 지원한다 — 이 저장소의 macOS(BSD 계열 grep 파생)에서도 동일 옵션으로 이미 그린이었으므로 위험도는 낮게 평가했다. 실제 Windows 러너에서 처음 실행해보고 깨지면(예: 오래된 grep 빌드) 이 표를 갱신하고 `verify` Windows 레그의 `continue-on-error`가 이미 흡수한다.
3. **경로 구분자**: `pnpm -r lint`가 실행하는 `apps/*/package.json`의 `lint` 스크립트(`cd ../.. && eslint apps/desktop/src ...`)는 슬래시(`/`) 경로를 리터럴 인자로 ESLint에 넘긴다. Node/ESLint는 Windows에서도 슬래시 경로를 그대로 받아들이므로 문제 없을 것으로 본다. 이 스크립트들은 `apps/*/package.json` 소유라 이 태스크(W2-09) 범위 밖이다 — 만약 Windows에서 실패하면 "Shared-file patch"로만 제안 가능.
4. **네이티브 Python 휠**: `engine`의 `ifcopenshell==0.8.5`, `manifold3d==3.5.2`, `shapely==2.1.2`, `numpy` 등은 PyPI에 `win_amd64`/`cp312` 휠이 모두 게시돼 있음을 워크플로 작성 시점에 PyPI JSON API로 직접 확인했다(빌드 필요 없음, 순수 wheel 설치). `trimesh`는 `py3-none-any` 순수 파이썬 휠이라 OS 무관. 따라서 `engine` 잡은 Windows에서도 `continue-on-error` 없이 필수로 뒀다 — 만약 실제 실행에서 특정 패키지가 소스 빌드로 떨어지며 실패하면(예: 새 패치 버전에서 미리 빌드된 wheel이 빠진 경우), 브리프의 기본값대로 해당 잡을 `continue-on-error: true`로 바꾸고 원인을 이 표에 기록한다(아직 미확정 — Questions for gate 참고).
5. **`verify` 잡의 Windows 레그**: 잡 전체를 `continue-on-error: true`로 뒀다(브리프 Constraints 지시). mac 레그만 필수. 이유: `tools/verify.sh`는 TS+엔진 전체를 다시 돌리는 무거운 스크립트라 `grep`/줄바꿈처럼 mac에서 검증 못한 변수가 겹쳐 있어 첫 실행에서 실패할 가능성을 배제할 수 없다.

## uv.lock / pnpm-lock.yaml 동결

두 워크플로 잡 모두 `--frozen`(pnpm: `--frozen-lockfile`, uv: `--frozen`)만 쓴다 — 잠금파일을 CI가 갱신하지 않는다. 잠금파일이 최신이 아니면 CI가 실패하는 것이 의도된 동작이다(로컬에서 `pnpm install` / `cd engine && uv sync`로 먼저 갱신하고 커밋한다).

## 비밀(secret)

이 워크플로는 어떤 GitHub Actions secret도 참조하지 않는다. `astral-sh/setup-uv`의 `github-token` 기본값(`${{ github.token }}`)만 암묵적으로 쓰인다(GitHub Releases 레이트리밋 완화용, 별도 설정 불필요).

## 확인된 Windows 차이 (CI 실행 #2~#4, 2026-09-02)

| 증상 | 원인 | 조치 |
|---|---|---|
| `astral-sh/setup-uv@v10` 해석 실패(양 OS) | 해당 액션은 메이저 별칭 태그를 만들지 않음 | 정확 태그 `v10.0.1` 고정 |
| ts(windows) exit 1 | 린트 픽스처 검사가 `pnpm`을 셸 없이 spawn(`.cmd` 심), ESLint 출력 경로가 백슬래시 | Node로 ESLint 직접 실행, 구분자 정규화, `.npmrc shell-emulator=true` |
| `test_ready_line_then_health` pid 불일치 | `halo-engine.exe` 런처가 파이썬을 자식으로 띄움 → Popen.pid ≠ READY.pid | 테스트는 READY pid 생존만 단언(POSIX는 등호 유지). 사이드카 종료는 프로세스 트리(`taskkill /T`) 필수 |
| `test_parent_pid_watch...` 엔진 미종료 | `os.kill(pid, 0)`이 Windows에서는 TerminateProcess이며 없는 PID에 OSError | `halo_engine.procutil.pid_alive`(OpenProcess/GetExitCodeProcess)로 교체 |

## Windows Installer 워크플로 (`.github/workflows/windows-installer.yml`, R1-00b)

이 파일은 위 `ci.yml`(lint/typecheck/test, 매 push·PR)과 별개다. 목적이 다르다 —
사용자는 Windows에서 **설치본으로만** 확인하므로(`docs/briefs/R1-00b.md`,
`docs/contracts/r1.md` §0), `main`·`task/**` 브랜치 푸시와 `workflow_dispatch`마다
`windows-latest` 한 잡에서 NSIS x64 설치본을 빌드해 아티팩트로 올린다. `ci.yml`은 이
태스크의 Forbidden 목록이라 변경하지 않았다 — 두 워크플로는 각자 독립적으로 트리거되고
캐시 키·동시성 그룹도 `${{ github.workflow }}`가 갈라 서로 간섭하지 않는다.

### 잡 구성

| 단계 | 내용 |
|---|---|
| 체크아웃 전 | `git config --global core.autocrlf false` (ci.yml과 동일한 사유) |
| Node/pnpm | `actions/setup-node@v7`(`.nvmrc`) → corepack → `pnpm install --frozen-lockfile` (pnpm 스토어는 `actions/cache@v6`로 캐시, ci.yml과 동일한 키 규칙) |
| Python/uv | `astral-sh/setup-uv@v10.0.1` → `uv python install 3.12` |
| 사이드카 | `bash engine/scripts/build-sidecar.sh` — Git Bash로 실행(브리프 제약: "Windows 셸은 bash 기본, PowerShell 전용 단계 없음"). `HALO_SIDECAR_SMOKE` 환경변수를 `workflow_dispatch`의 `skip_sidecar_smoke` 입력에서 계산해 넘긴다(기본은 스모크 체크 실행) |
| 빌드 | `pnpm build` (apps/web dist + apps/desktop out, 스키마 패키지는 pnpm의 워크스페이스 의존 그래프가 위상 정렬로 먼저 빌드함 — `tools/package.sh`와 동일 순서, 로컬에서 mac으로 검증) |
| 패키징 | `pnpm --filter @halo-cad/desktop build:app` — `apps/desktop/electron-builder.yml`의 `win`/`nsis` 설정으로 NSIS x64 설치본 생성 |
| 업로드 | `actions/upload-artifact@v4`, 이름 `halo-dwg-revision-windows-x64`, 대상 `dist/*.exe` + `dist/latest.yml`, 보존 14일. 실패 시에만 `engine/build`·`engine/dist`·`dist` 전체를 별도 아티팩트(`-failure-logs`, 보존 7일)로 올린다 |

동시성은 ci.yml과 같은 패턴(`${{ github.workflow }}-${{ github.ref }}`, `cancel-in-progress: true`)
— 같은 브랜치에 새 push가 오면 이전 빌드를 취소한다.

### `latest.yml`이 생성되지 않는 이유

브리프는 아티팩트 구성을 "`*.exe` + `latest.yml`"로 적었지만, 로컬 mac 빌드로 실측한 결과
`latest.yml`(electron-updater 갱신 메타파일)은 **생성되지 않는다**. electron-builder는
`build.publish` 설정이 없으면 `package.json`의 `repository` 필드나 `.git/config`의
`origin`이 `github.com`(또는 인식되는 다른 호스트)을 가리켜야만 업데이트 메타파일을
만든다(`app-builder-lib`의 `getPublishConfigsForUpdateInfo`, 소스: `node_modules/.pnpm/
app-builder-lib@26.15.3.../out/publish/updateInfoBuilder.js`) — 이 저장소는 `repository`
필드가 없고 `git remote -v`도 로컬 경로(`halo-cad-local`)뿐이라 어느 쪽도 해당하지 않는다.
CLAUDE.md가 자동 업데이트(`publish` 설정) 자체를 금지하므로 이는 오히려 의도에 맞는
상태다 — 워크플로는 `latest.yml`이 없어도 실패하지 않도록 `if-no-files-found: warn`으로
뒀다(`dist/*.exe`는 항상 매치하므로 업로드 자체는 항상 성공한다). 원격이 GitHub로
바뀌거나 `repository` 필드가 추가되면 이 절을 재확인한다.

### 미검증 항목

이 저장소에는 아직 GitHub 원격이 없어(`git remote -v`, `halo-cad-local`뿐) 이 워크플로가
실제 `windows-latest` 러너에서 실행된 적이 없다. R1-00b가 확인한 것은 (a) YAML 파싱
유효성(`python -c "import yaml; yaml.safe_load(...)"`), (b) `engine/halo-engine.spec`·
`engine/scripts/build-sidecar.sh`의 OS 분기 로직이 mac에서 기존 동작을 깨지 않음(READY
스모크 그대로 통과), (c) `apps/desktop/electron-builder.yml`에 `win`/`nsis` 블록을
추가해도 mac dmg/zip 빌드가 그대로 성공함, (d) `docs/dev/ci.md`(이 문서, 위 표)에 이미
기록된 Windows 차이(CRLF, taskkill, pid 불일치)를 build-sidecar.sh에도 동일하게
반영했다는 점이다. 실제 `windows-latest` 러너에서의 첫 실행 결과(sips로 만든 아이콘이
electron-builder에서 정상적으로 `.ico`로 변환되는지, NSIS 빌드 자체가 통과하는지 등)는
원격이 생기고 처음 push된 뒤 이 절을 실측 결과로 갱신해야 한다.
