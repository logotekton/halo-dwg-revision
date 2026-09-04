# 패키징 (macOS arm64)

`tools/package.sh`가 사이드카(PyInstaller)와 데스크톱 앱(electron-builder)을 빌드해 dmg/zip을 만든다.
W2-08 범위는 **macOS arm64만**이다(Intel/Windows는 W5-05, CI).

## 요구사항

- `docs/dev/setup.md`의 개발 환경(Node 24, pnpm 10, `pnpm install`) 그대로.
- `uv`(엔진 사이드카 빌드). `PATH`에 `uv`가 있어야 한다(`$HOME/.local/bin/uv` 폴백).
- Xcode Command Line Tools의 `codesign`, `sips`, `iconutil`, `hdiutil`(모두 macOS 기본 제공). **Apple 개발자 서명 인증서나 공증(notarization) 계정은 필요 없다** — 이 단계는 ad-hoc 서명만 한다.

## 실행

```bash
tools/package.sh
```

순서(고정, 실패 시 `set -euo pipefail`로 즉시 중단):

1. `engine/scripts/build-sidecar.sh` — PyInstaller onedir 사이드카 빌드 → `engine/dist/halo-engine/`. 빌드 후 그 자리에서 `halo-engine serve --dev --port 0 --token dev`를 실행해 READY 라인이 나오는지 확인한다(번들 자체의 스모크 체크).
2. `pnpm build` — `apps/web/dist`(Vite)와 `apps/desktop/out/{main,preload}`(electron-vite) 빌드.
3. `pnpm --filter @halo-cad/desktop build:app` — `electron-builder --config electron-builder.yml`. dmg + zip을 만든다.

산출물(리포 루트, `.gitignore`의 `dist/`):

```
dist/Halo CAD-<version>-arm64.dmg
dist/Halo CAD-<version>-arm64-mac.zip
dist/mac-arm64/Halo CAD.app/          # electron-builder의 압축 전 unpacked 결과물. smoke-packaged.mjs가 이 경로를 직접 실행한다.
```

사이드카만 다시 빌드하려면 `engine/scripts/build-sidecar.sh`를 단독 실행해도 된다(`engine/dist/halo-engine/`만 갱신).

### 개별 스모크 체크

```bash
# 1) 사이드카 단독 실행(번들 안에 있는 그대로)
engine/dist/halo-engine/halo-engine serve --dev --port 0 --token dev | head -1
# -> {"event": "ready", "port": N, "pid": P, "version": "0.0.1"}

# 2) 패키지된 앱(설치본과 동일한 바이너리, dmg를 마운트하지 않고 unpacked 결과를 바로 실행)
node apps/desktop/scripts/smoke-packaged.mjs
# -> E2E_WINDOW_TITLE:Halo CAD, exit 0 (120초 이내)
```

`smoke-packaged.mjs`는 main 프로세스의 `HALO_E2E_SMOKE=1` 훅(`apps/desktop/src/main/window.ts`, `docs/dev/setup.md`와 동일한 메커니즘)으로 앱을 띄우고 창 제목과 종료 코드를 확인한다. W2-01의 사이드카 IPC(`halocad:engine:get-connection`)가 preload에 아직 없으면 상태바 "연결됨" 스크린샷 확인은 건너뛴다(로그에 이유가 출력된다) — 브리프의 "Defaults for ambiguity"대로다.

## 리소스 레이아웃 (계약: `docs/contracts/wave-2.md` "패키징")

`apps/desktop/electron-builder.yml`의 `extraResources`가 다음을 만든다.

```
Halo CAD.app/Contents/Resources/
├── engine/              ← engine/dist/halo-engine/ 전체 (halo-engine 실행 파일 + _internal/)
└── web/                 ← apps/web/dist/ 내용물 그대로 (index.html이 web/ 바로 아래, web/dist/ 아님)
```

패키지 여부에 따른 분기 규칙(계약대로):

```
app.isPackaged
  ? join(process.resourcesPath, 'web')       // 패키지: <Resources>/web
  : join(app.getAppPath(), '..', 'web', 'dist')  // 개발/언패키지: apps/desktop 옆의 apps/web/dist
```

이 로직은 `apps/desktop/src/main/protocol.ts`의 `resolveWebDistDir()`로 구현하고 단위 테스트했다(`protocol.test.ts`). **알려진 제한사항**: 이 함수를 실제로 호출하는 곳은 `apps/desktop/src/main/index.ts`인데, 그 파일은 이 태스크 소유가 아니라서(다른 태스크가 사이드카 배선을 소유) 고치지 못했다 — 지금 `index.ts`의 `webDistDir()`는 `app.isPackaged`로 분기하지 않고 언제나 `join(app.getAppPath(), '..', 'web', 'dist')`를 쓴다. 그 결과 **패키지된 앱을 실제로 열면 `halocad://app/index.html`이 404("Not Found")로 뜬다** (`Contents/Resources/web/dist`를 찾는데 실제 파일은 `Contents/Resources/web/`에 있어서). 창 제목은 고정 문자열(`strings.ko.json`)이라 이 문제와 무관하게 정상 출력되므로 `smoke-packaged.mjs`는 통과한다. 필요한 수정은 보고서의 "Shared-file patch"에 정확한 diff로 남겼다 — `index.ts` 소유 태스크(또는 병합 시 Fable)가 적용해야 한다.

## 사이드카 스펙 (`engine/halo-engine.spec`)

`engine/scripts/build-sidecar.sh`가 `uv run --with pyinstaller==6.22.0 pyinstaller engine/halo-engine.spec`로 빌드한다. `pyinstaller`는 `engine/pyproject.toml`(이 태스크 소유 아님)에 추가하지 않고 `uv run --with`의 일회성 오버레이로만 쓴다 — `uv.lock`도 건드리지 않는다.

- `collect_all()`로 강제 수집: `ifcopenshell`(express 스키마 데이터 + `ifcopenshell.api`의 동적 임포트 서브모듈), `shapely`(자체 번들 GEOS dylib), `manifold3d`, `trimesh`. 오늘 시점의 `halo_engine` 소스는 이 라이브러리들을 아직 임포트하지 않지만(`model/`, `rules/`, `geometry/`가 아직 스텁), 나중 태스크가 쓰기 시작하기 전에 바이너리/데이터 수집 자체가 되는지 미리 증명하는 것이 이 스파이크의 목적이다.
- `copy_metadata()`로 버전 메타데이터 포함: `ezdxf`, `shapely`, `manifold3d`, `trimesh`, `ifcopenshell`, `numpy`, `fastapi` — `/api/v1/system/health`가 `importlib.metadata.version()`으로 읽는 것과 정확히 같은 목록. 번들 실행 후 확인:
  ```json
  {"status":"ok","version":"0.0.1","python":"3.12.14","deps":{"ezdxf":"1.4.4","shapely":"2.1.2","manifold3d":"3.5.2","trimesh":"5.1.0","ifcopenshell":"0.8.5","numpy":"2.5.2","fastapi":"0.141.1"}}
  ```
- uvicorn(`uvloop` 미설치, CLAUDE.md 핀 그대로)의 문자열 기반 런타임 선택(`loops.auto`, `protocols.http.auto`)과 typer/click/shellingham을 hidden import로 명시.
- `excludes=["mypy", "hypothesis", "pytest", "_pytest", "ruff"]` — `engine`의 uv 워크스페이스 `.venv`는 dev 그룹(mypy/hypothesis/pytest/ruff)까지 함께 설치돼 있고, `pydantic`이 선택적 플러그인 shim(`pydantic.mypy`, `pydantic.v1._hypothesis_plugin`)에서 이들을 모듈 최상단에 `import`하기 때문에 정적 분석이 실사용 여부를 모른 채 그대로 번들에 끌고 온다. 런타임에 전혀 쓰이지 않으므로 제외한다(제외 전 248M → 제외 후 238M).
- `shapely.tests.*`/`conftest`도 `collect_all()`이 함께 쓸어 담길 수 있어 명시적으로 걸러낸다.

## Gatekeeper 우회 (서명·공증 없음)

이 환경은 Apple 개발자 서명 인증서나 공증 계정이 없어 **ad-hoc 서명**만 한다(`electron-builder.yml`: `identity: null`, `hardenedRuntime: false`). dmg를 열어 앱을 `/Applications`로 드래그한 뒤 처음 실행하면 macOS가 "확인되지 않은 개발자" 경고로 실행을 막는다. 사내 전용 배포이므로 다음 중 하나로 연다.

1. **시스템 설정 경로(권장)**: 앱을 한 번 실행 시도 → 경고 대화상자에서 "취소" → **시스템 설정 → 개인정보 보호 및 보안** → 아래로 스크롤 → "'Halo CAD'이(가) 실행되지 않았습니다" 옆의 **"그래도 열기"** 클릭 → 다시 앱 실행 시 "열기" 확인.
2. **우클릭 열기**: Finder에서 `Halo CAD.app`을 우클릭(또는 Control+클릭) → **"열기"** → 확인 대화상자에서 다시 **"열기"**.
3. **터미널(quarantine 속성 제거)**: 브라우저로 내려받아 quarantine 플래그가 붙은 경우만 필요.
   ```bash
   xattr -dr com.apple.quarantine "/Applications/Halo CAD.app"
   ```
   이 저장소에서 직접 빌드한 dmg는 Finder/브라우저를 거치지 않는 한 quarantine 속성이 붙지 않는다(로컬 빌드 확인됨: `xattr -l`에 `com.apple.quarantine` 없음, `com.apple.provenance`만 있음) — 사내에서 dmg를 공유(에어드랍, 사내 파일 공유 등)하면 붙을 수 있으므로 1번/2번 절차를 우선한다.

## Windows (NSIS x64, R1-00b)

사용자는 Windows에서 **설치본으로만** 확인한다 — 개발 체크아웃도 셀프호스티드 러너도 없다
(`docs/briefs/R1-00b.md`). `.github/workflows/windows-installer.yml`이 `main`·`task/**`
푸시마다 GitHub Actions `windows-latest`에서 빌드한다. 순서는 macOS의 `tools/package.sh`와
같다: ① `engine/scripts/build-sidecar.sh`(Git Bash, `halo-engine.exe` onedir) ② `pnpm build`
③ `pnpm --filter @halo-cad/desktop build:app`(electron-builder NSIS x64). 산출물은 Actions
아티팩트 `halo-dwg-revision-windows-x64`(보존 14일)로 올라간다.

### 사이드카(Windows)

`engine/halo-engine.spec`은 `sys.platform`으로 분기한다: `target_arch`는 macOS 링커
전용 옵션이라 darwin에서만 넘기고(Windows/Linux는 `None`), comtypes(ADR-0007)는
`sys_platform == 'win32'` 환경 마커로만 설치되므로 `collect_all("comtypes")`도 Windows
빌드에서만 호출한다(그렇지 않으면 comtypes가 없는 mac 빌드 환경에서
`ModuleNotFoundError`). `engine/scripts/build-sidecar.sh`는 `uname -s`/`OS` 환경변수로
Windows를 감지해 실행 파일 이름에 `.exe`를 붙이고, READY 스모크 체크의 프로세스 종료를
`taskkill //PID <pid> //T //F`로 한다(트리 종료 필요, `docs/dev/ci.md`의 "스폰 pid ≠
서버 pid" 참고 — `//`는 Git Bash의 MSYS 경로 변환이 `/PID`·`/T`·`/F`를 윈도우 경로로
오인하지 않게 하는 관용적 우회다). 이 스모크 체크가 CI 러너의 포트 바인딩 문제로 실패하면
`HALO_SIDECAR_SMOKE=0` 환경변수로 건너뛸 수 있다(워크플로의 `workflow_dispatch` 입력
`skip_sidecar_smoke`로 켤 수 있음) — 기본은 항상 실행.

### electron-builder(Windows)

`apps/desktop/electron-builder.yml`의 `win` 블록: `target: nsis`, `arch: [x64]`, 아이콘은
`build/icon.png`(mac `build/icon.icns`에서 `sips -s format png icon.icns --out
build/icon.png -Z 512`로 512px PNG 추출 — electron-builder가 단일 PNG에서 다중 해상도
`.ico`를 자동 생성하므로 `.ico`를 직접 만들 필요가 없다). `nsis` 블록: `oneClick: false`
+ `allowToChangeInstallationDirectory: true`(설치 경로를 사용자가 바꿀 수 있는 어시스트형
설치 마법사), `perMachine: false`(사용자별 설치, 관리자 권한 불필요), `language: '1042'`
+ `installerLanguages: ['ko_KR']` + `multiLanguageInstaller: false`(한국어 고정 UI,
CLAUDE.md "한국어 UI"). 산출물 이름은 electron-builder 기본값
`Halo CAD Setup <version>.exe`.

### 코드 서명 없음 (SmartScreen 경고만)

이 환경에는 Windows 코드 서명 인증서가 없다(CLAUDE.md/브리프 제약). 설치본은 서명되지
않은 채로 배포되며, 처음 실행 시 Windows SmartScreen이 "Windows에서 PC를 보호했습니다"
경고를 띄운다 — 사내 전용 배포이므로 "추가 정보" → "실행"으로 진행한다. 자동 업데이트
(`electron-builder`의 `publish` 설정)는 구성하지 않았다(CLAUDE.md "런타임 외부 네트워크
없음").

### 사용자 절차 (다운로드 → 설치 → 실행 → 로그)

1. GitHub Actions의 `Windows Installer` 워크플로 실행 목록에서 확인하려는 커밋의 실행을
   연다 → Artifacts에서 `halo-dwg-revision-windows-x64.zip`을 내려받는다(14일 안에
   내려받아야 한다 — 만료되면 같은 브랜치를 다시 푸시하거나 `workflow_dispatch`로 재실행).
2. zip을 풀면 `Halo CAD Setup <version>.exe`가 나온다. 더블클릭해 실행한다.
3. SmartScreen 경고가 뜨면 "추가 정보" → "실행"(위 "코드 서명 없음" 참고).
4. 한국어 설치 마법사가 뜬다 — 설치 경로를 바꾸려면 이 단계에서 지정한다(기본은
   `%LOCALAPPDATA%\Programs\Halo CAD`, `perMachine: false`이므로 관리자 권한 불필요).
   "설치" → 완료 후 "Halo CAD 실행" 체크박스를 두거나 시작 메뉴에서 직접 실행한다.
5. 앱이 뜨지 않거나 "엔진 시작 실패" 상태바가 보이면 로그를 확인한다:
   `%APPDATA%\Halo CAD\logs\engine.log`(회전 로그, 최대 5개 —
   `docs/dev/engine-sidecar.md` "로그 위치"와 같은 메커니즘, Windows에서는
   `app.getPath('userData')`가 `%APPDATA%\Halo CAD`로 해석된다). 문제를 보고할 때는 이
   파일을 첨부한다.

## 알려진 제한사항 / 후속 작업

- **`index.ts`의 `isPackaged` 분기 미적용** (위 "리소스 레이아웃" 참조) — 병합 시 `apps/desktop/src/main/index.ts`에 `resolveWebDistDir()` 배선 필요.
- ifcopenshell 하나가 onedir 크기의 대부분(`_internal/ifcopenshell` 약 175MB, 컴파일된 `_ifcopenshell_wrapper*.so`가 그중 대부분)을 차지한다. 향후 산출물 크기를 줄이려면 `--onefile`(콜드 스타트 비용과 트레이드오프) 또는 필요 시점까지 ifcopenshell을 지연 로드하는 방향을 검토할 수 있다(이번 스파이크 범위 밖).
- Intel(x64) mac 패키징은 아직 범위 밖(추후 태스크). Windows 패키징/CI는 R1-00b에서 이 문서와 `docs/dev/ci.md`의 "Windows Installer 워크플로"로 완료됐다 — 단, 이 저장소에 아직 GitHub 원격이 없어 워크플로 자체가 실제 Windows 러너에서 실행된 적은 없다(YAML 파싱 검사와 로컬 mac 검증만 마쳤다, `docs/briefs/R1-00b.md` 보고서 참고). 원격이 생기고 처음 push되면 실제 실행 결과로 이 절을 갱신해야 한다.
- `latest.yml`(electron-updater용 업데이트 메타파일)은 이 저장소에 `repository` 필드나 GitHub 리모트가 없어 생성되지 않는다(electron-builder가 publish 대상을 못 찾음) — 자동 업데이트를 쓰지 않으므로(CLAUDE.md) 의도된 상태다. 워크플로는 이 파일이 없어도 실패하지 않는다(`if-no-files-found: warn`).
- 아이콘(`build/icon.png`)은 `build/icon.icns`와 동일하게 알파 채널이 없다(원본 아이콘 자체가 불투명 RGB) — 둥근 모서리 밖 배경이 흰 사각형으로 보일 수 있다. 투명 아이콘이 필요해지면 별도 태스크에서 알파 채널이 있는 원본을 새로 준비해야 한다.
