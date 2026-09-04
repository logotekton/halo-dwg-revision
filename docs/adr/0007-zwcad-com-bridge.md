# ADR-0007 ZWCAD COM 브리지: comtypes 채택

상태: 승인 (2026-09-04)

## 맥락

R1 MVP는 배경 ZWCAD(사용자가 이미 설치한 사내 표준 CAD)를 자동화해 DWG ↔ DXF를 변환한다
(CLAUDE.md 절대 규칙 2: "변환은 배경 ZWCAD(COM) 우선, 없으면 ADR-0002의 자체 변환기").
ZWCAD는 AutoCAD와 호환되는 ActiveX/COM Automation 서버(`ZWCAD.Application` ProgID)를
Windows에만 제공한다. Python에서 이 COM 서버를 구동하려면 COM 바인딩 라이브러리가 필요하고,
`engine/`의 PyInstaller 사이드카(`engine/halo-engine.spec`)가 이를 onedir 번들에 포함해야
한다. 인터페이스 계약은 `docs/contracts/r1.md` §6.1(`zwcad.py`, R1-02가 구현)에 이미
고정돼 있다 — 이 ADR은 그 계약이 어떤 COM 바인딩 라이브러리 위에서 동작하는지를 정한다.

## 검토한 대안

- **pywin32 (PSF 유사 라이선스 + 일부 BSD/MS-PL 혼재, 실질적으로 소스가 공개돼 있으나
  단일 OSI 승인 라이선스로 분류되지 않고 `pywin32-ctypes`/`pypiwin32` 등 배포명이 갈라짐)**.
  CLAUDE.md 절대 규칙 3의 허용 목록(MIT/BSD/Apache/MPL/OFL)에 명확히 들지 않는다. 또한
  pywin32는 설치 후 `pywin32_postinstall.py`를 실행해 `pythoncom*.dll`을 `System32`나
  파이썬 `DLLs/`에 등록해야 정상 동작하는 경우가 많다 — PyInstaller onedir처럼 격리된
  실행 환경에서는 이 설치 후처리가 없어 COM 마샬링이 깨지는 사례가 흔하다(별도 `pywin32
  --install` 단계나 커스텀 훅이 필요). 사이드카는 "압축 풀고 실행"이 계약이므로(패키징
  계약, `docs/dev/packaging.md`) 설치 후처리가 필요한 라이브러리는 배제한다. → 기각
  (라이선스 허용 목록 밖 + 설치 후처리 요구).
- **comtypes (MIT, 채택)**. 순수 Python(ctypes 기반), 설치 후처리 없음 — `pip`/`uv`로
  넣으면 그대로 동작한다. 타입 라이브러리를 런타임에 읽어 COM 인터페이스를 동적으로
  생성하므로 사전 컴파일된 바인딩이 필요 없다. GitHub(enthought/comtypes)의
  `LICENSE.txt`가 표준 MIT 문구 그대로다(저작권 Thomas Heller 2006-2013, Comtypes
  Developers 2014). CLAUDE.md 허용 목록에 맞는다.

## 결정

1. **comtypes 1.4.16을 채택한다** (2026-09-04 시점 PyPI 최신 안정판, MIT).
   `engine/pyproject.toml`의 `dependencies`에 환경 마커로 넣는다:
   `comtypes==1.4.16; sys_platform == 'win32'` — macOS/Linux 개발 환경·CI 레그에는
   설치되지 않는다(`uv sync --frozen`이 마커를 보고 건너뜀, 실측: `cd engine && uv sync
   --frozen`이 mac에서 comtypes 없이 성공).
2. **pywin32는 쓰지 않는다.** 위 "검토한 대안" 사유(라이선스 허용 목록 밖, 설치 후처리)로
   영구 배제한다. 향후 comtypes로 해결되지 않는 COM 기능이 발견되면 이 ADR을 대체하는
   새 ADR로만 재검토한다.
3. **숨은 인스턴스 관리.** `ZwcadConverter`(`engine/src/halo_engine/compare/zwcad.py`,
   R1-02 구현, 계약은 `docs/contracts/r1.md` §6.1)는 `comtypes.client.CreateObject
   ("ZWCAD.Application")`로 프로세스당 인스턴스 하나만 만들고 `Visible=False`로 화면에
   띄우지 않는다. `with` 블록 진입 시 시스템 변수 `FILEDIA=0`, `CMDDIA=0`,
   `PROXYNOTICE=0`, `FONTALT=malgun.ttf`를 설정해 파일 다이얼로그·프록시 경고·누락 폰트
   대체를 사용자 개입 없이 통과시킨다. 열기는 읽기 전용
   (`Documents.Open(path, ReadOnly=True)`, CLAUDE.md 절대 규칙 1 "원본 불변"과 정합),
   저장은 `SaveAs(out, <DXF 버전 상수>)` 후 `Close(False)`.
4. **시간 제한과 재기동.** 파일당 `timeout_s`(기본 120초) 안에 변환이 끝나지 않으면
   프로세스 트리를 강제 종료하고(대기 중인 COM 호출이 영구 블록되는 ZWCAD 특유의 실패
   모드 대응 — 대화상자가 뜨는데 `Visible=False`라 사용자가 응답할 수 없는 경우 등)
   `restart()`로 새 숨은 인스턴스를 올린 뒤 `ZwcadTimeout`을 던진다. 호출자(R1-03의 잡
   러너)는 이를 그 파일에 대한 실패로 기록하고 다음 파일로 넘어간다 — 한 파일의 타임아웃이
   전체 세트 인입을 막지 않는다.
5. **`comtypes.client.gen_dir` 쓰기 위치.** comtypes는 타입 라이브러리를 처음 읽을 때
   생성된 바인딩 모듈을 캐시 디렉터리(`comtypes.gen`)에 파일로 쓴다. 기본값(설치 경로
   옆)은 PyInstaller onedir 번들(읽기 전용으로 취급, 재배포 시 덮어써짐)이나 프로그램
   파일 권한이 제한된 설치 위치에 쓰기를 시도해 실패할 수 있다. `cli.py`의 엔진 기동
   경로에서 `comtypes.client.gen_dir`를 `%LOCALAPPDATA%/halo/comtypes_gen`로 명시
   설정한다(디렉터리 없으면 생성) — CLAUDE.md 절대 규칙 1의 "쓰기는 `.halo/`와 `출력/`에만"
   은 사용자 프로젝트 데이터에 대한 규칙이고, 이 경로는 사용자별 앱 캐시(엔진의 `--data-dir`
   와 같은 계열의 위치, `docs/dev/engine-sidecar.md`의 로그 위치 `%APPDATA%/Halo CAD/`
   와 나란한 `%LOCALAPPDATA%` 쪽)라 원본·번들과 무관하다. 이 설정은 R1-02가
   `zwcad.py`/`cli.py`에서 구현한다(이 태스크 R1-00b는 ADR만 기록).
6. **PyInstaller 수집.** `engine/halo-engine.spec`은 `sys.platform == "win32"`일 때만
   `collect_all("comtypes")`로 comtypes 본체와 그 하위 모듈을 강제 수집한다(마커 때문에
   macOS 빌드 환경에는 애초에 설치돼 있지 않으므로, 무조건 호출하면
   `ModuleNotFoundError`로 mac 사이드카 빌드가 깨진다 — 플랫폼 분기가 필수). comtypes는
   동적으로 `comtypes.gen.<TypeLibCLSID>` 형태의 하위 모듈을 런타임에 생성하므로 정적
   분석(PyInstaller의 기본 임포트 추적)이 이들을 미리 볼 수 없다 — 5번 항목의
   `gen_dir` 재배치가 "생성된 바인딩을 쓰기 가능한 사용자별 위치에 캐시"하는 것으로
   이 한계를 보완한다(번들 안에 미리 굽지 않고 최초 실행 시 생성).
7. **macOS 스텁과 계약 테스트.** `detect()`는 macOS/Linux에서 `ZwcadStatus(available=False,
   installed=False, version=None, prog_id=None, reason="not_windows")`를 반환하고,
   `ZwcadConverter()` 생성 시도는 즉시 `ZwcadUnavailable`을 던진다 — comtypes 자체가
   이 플랫폼에 설치돼 있지 않으므로 임포트 시점이 아니라 `detect()`/생성자 호출 시점에
   플랫폼을 먼저 확인한다. 계약 테스트(`docs/contracts/r1.md` §6.1의 `ComBackend`
   프로토콜 인용)는 실제 COM 대신 `ComBackend`(가짜로 교체 가능한 유일한 경계 —
   `create_app(prog_id) -> Any`, `kill_process_tree(pid) -> None`)를 페이크로 주입해
   Windows 경로(정상 변환, 타임아웃, 재기동)를 macOS 포함 모든 CI 러너에서
   시뮬레이션한다. 실제 ZWCAD COM 서버를 구동하는 통합 테스트는 Windows 전용이며 사내
   ZWCAD 설치가 있는 머신에서만 수동/게이트 확인으로 돈다(`docs/gates/R1.md`).

## 결과

- `engine/pyproject.toml`에 `comtypes==1.4.16; sys_platform == 'win32'` 한 줄이 추가되고
  `uv.lock`이 갱신된다(cross-platform 해석이라 mac에서도 `uv lock` 실행 가능, 설치는
  win32에서만). 라이선스: MIT.
- `engine/halo-engine.spec`이 Windows 빌드에서만 comtypes를 수집한다.
- `ZwcadConverter`·`detect()`의 실제 구현, `gen_dir` 재배치, `api/routers/compare_zwcad.py`
  라우터는 R1-02 범위다(`engine/src/halo_engine/compare/**`는 이 태스크의 Forbidden).
- pywin32에 대한 향후 재검토는 반드시 새 ADR로 이 ADR을 "대체됨"으로 바꿔야 한다.

## 후속

- [ ] R1-02: `zwcad.py`·`ComBackend`·계약 테스트·`gen_dir` 재배치 구현.
- [ ] R1-02: 실제 ZWCAD 설치본으로 `detect()`·타임아웃·재기동을 사내 Windows 머신에서
      1회 수동 검증하고 `docs/gates/R1.md`에 `R1-GATE zwcad-com: PASS|FAIL` 기록.
