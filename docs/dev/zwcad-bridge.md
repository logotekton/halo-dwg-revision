# ZWCAD COM 브리지 (R1-02)

숨은(`Visible=False`) ZWCAD 인스턴스 하나를 이 프로세스 안에서 `comtypes`(MIT)로 띄워 DWG↔DXF를
변환한다. `pywin32`는 쓰지 않는다(ADR-0007, 라이선스 허용 목록 밖). 계약은 `docs/contracts/r1.md`
§6.1, 구현은 `engine/src/halo_engine/compare/zwcad.py`, 라우터는
`engine/src/halo_engine/api/routers/compare_zwcad.py`. macOS·Linux에서는 전부 스텁이다 — 개발은
이 저장소를 체크아웃한 macOS에서 하고, 실제 자동화는 사용자가 Windows 설치본으로만 확인한다.

## 동작 순서

1. `ZwcadConverter(timeout_s=120, dxf_version="2013")` 생성 시 ProgID 후보
   (`ZWCAD.Application.2026` → `ZWCAD.Application`, 신형부터)를 차례로 시도해 COM 인스턴스를
   하나 만든다. 전부 실패하면 `ZwcadUnavailable`.
2. 인스턴스가 뜨면 곧바로 `Visible=False`, `SetVariable("FILEDIA", 0)`, `SetVariable("CMDDIA", 0)`,
   `SetVariable("PROXYNOTICE", 0)`을 건다 — 이 넷 중 하나라도 실패하면 대화상자가 자동화를 막을
   수 있으므로 **치명**(`ZwcadError`)으로 다룬다. `SetVariable("FONTALT", "malgun.ttf")`는
   실패해도 텍스트 렌더링만 나빠질 뿐 자동화를 막지 않으므로 경고만 남기고 계속한다.
3. 파일 하나를 변환할 때: `Documents.Open(path, True)`(읽기 전용) →
   `doc.SaveAs(out_path, <SaveAs 버전 상수>)` → `doc.Close(False)`(저장 안 함, 원본은 애초에
   읽기 전용으로 열었다). 이 세 COM 호출은 **호출 스레드에서** 실행한다 — ZWCAD의 Application은
   STA COM 객체라 만든 스레드에서만 안전하게 쓸 수 있기 때문이다. 별도 감시 스레드는 시간만 재고,
   시간 초과 시 프로세스 트리만 죽인다(감시 스레드가 호출 스레드의 블로킹 호출에 직접 끼어들
   방법은 없다).
4. 파일당 `timeout_s`(기본 120초)를 넘기면 감시 스레드가 `kill_process_tree(pid)`로 프로세스
   트리를 죽이고 `restart()`로 새 인스턴스를 띄운 뒤, 호출 스레드 쪽에는 `ZwcadTimeout`이
   올라간다(죽은 프로세스 위에서 걸려 있던 호출이 무엇을 반환하든 버린다).
5. `with` 블록을 나올 때(`__exit__`) `Quit()`을 호출하고, PID를 알고 있고 그 프로세스가 아직
   살아 있으면(`procutil.pid_alive`) `kill_process_tree`로 강제 종료한다.

## PID 확보

`Application.HWND` → `GetWindowThreadProcessId`(Win32 API, `ctypes`)로 프로세스 ID를 얻는다.
`psutil`은 의존성 허용 목록 밖이라 쓰지 않았고, 프로세스 트리 종료 자체는 `taskkill /PID <pid> /T
/F`(하위 프로세스까지 한 번에 정리, 별도 열거 불필요)로 한다. HWND를 못 읽거나 PID 변환이
실패하면 `Quit()`만 호출하고 경고 로그만 남긴다(브리프 Constraints 기본값) — 이 경우 시간 초과가
나도 프로세스 트리는 죽이지 못한 채 재시작만 시도한다.

## 시스템 변수

| 변수 | 값 | 실패 시 |
|---|---|---|
| `FILEDIA` | `0` | 치명 (`ZwcadError`) |
| `CMDDIA` | `0` | 치명 |
| `PROXYNOTICE` | `0` | 치명 |
| `FONTALT` | `malgun.ttf` | 경고만, 계속 |

## `comtypes.client.gen_dir`

PyInstaller로 만든 설치본은 실행 파일 옆 폴더가 쓰기 불가능할 수 있어, comtypes가 생성한 타입
라이브러리 래퍼 캐시를 `%LOCALAPPDATA%/halo/comtypes_gen`에 둔다(`LOCALAPPDATA`가 없으면
`tempfile.gettempdir()/halo_comtypes_gen`). `ComtypesBackend.create_app`이 인스턴스를 만들기
전에 이 폴더를 만들고 `comtypes.client.gen_dir`을 거기로 돌린다.

## SaveAs 버전 상수

```python
SAVE_AS_VERSIONS = {
    "ac2000_dxf": 13,
    "ac2007_dxf": 37,
    "ac2013_dwg": 60,
    "ac2013_dxf": 61,
    "ac2018_dwg": 64,
    "ac2018_dxf": 65,
}
```

**전제(미확인):** ZWCAD의 `ZcSaveAsType` 열거값이 AutoCAD의 `AcSaveAsType`와 1:1로 같다고 보고
그대로 옮겼다. 실제로 다르면 이 dict 하나만 고치면 된다 — 호출부(`_dxf_save_as_key`,
`_dwg_save_as_key`)는 값을 몰라도 된다. 확인 절차는 아래 "Windows 수동 확인" 참고. 게이트 질문
Q6(`docs/gates/R1-questions.md`)로 이미 올라가 있다.

## `detect()`가 실제 COM 인스턴스를 띄우지 않는 이유

계약 문구("설치 감지는 winreg로 CLSID 존재 확인 + 버전은 app.Version 문자열")를 문자 그대로
따르면 상태 조회 때마다 숨은 ZWCAD를 띄웠다 죽여야 한다. `GET /compare/zwcad/status`는 데스크톱
UI가 자주 찌를 수 있는 엔드포인트라 부작용 없는 쪽을 택했다:

- 설치 여부·ProgID는 레지스트리(`HKCR\<ProgID>\CLSID`)만 본다.
- 버전은 등록된 ProgID 자체의 버전 접미사(`ZWCAD.Application.2026` → `"2026"`)에서 뽑는다.
  접미사가 없는 `ZWCAD.Application`만 등록돼 있으면 `version=None`으로 둔다(설치는 됐지만
  버전 문자열은 모른다는 뜻 — `available`에는 영향 없음).
- 실제 변환 시작(`ZwcadConverter.__init__`)에서는 인스턴스를 띄운 뒤 진짜 `Application.Version`을
  읽어 `ConvertResult.zwcad_version`에 담는다 — 여기서는 인스턴스를 어차피 띄우므로 추가 비용이
  없다.

Windows 수동 확인에서 레지스트리 파생 버전과 실제 `Application.Version`이 다르면(예: 접미사가
빌드 번호를 담고 실제 마이너 버전과 다른 경우) 이 문서와 `_version_from_prog_id`를 갱신한다.

## Windows 수동 확인 절차 (R1-11 게이트)

개발 전체가 macOS에서 이뤄지므로, 이 브리지가 **진짜 ZWCAD 2026 Professional**과 맞물려 돌아가는
것은 사용자가 Windows 설치본으로만 확인한다. `tools/verify.sh`·`pytest`는 전부 `FakeComBackend`로
COM 호출 순서·시간 제한·재시작 로직만 증명하며, 실제 자동화 성공 여부는 증명하지 않는다.

1. R1-00b(또는 이후 최신) GitHub Actions `windows-latest` 아티팩트에서 설치본을 받아 설치한다.
2. ZWCAD 2026 Professional이 같은 PC에 설치·라이선스 활성화돼 있는지 확인한다(자동화는 별도
   실행 중인 ZWCAD 창이 없어도 되지만, 설치·등록은 되어 있어야 한다).
3. 설치본 폴더 안 사이드카 실행 파일로 최소 **5장**을 변환해 본다(경로는 실제 설치 위치에 맞게
   바꾼다):

   ```powershell
   cd "<설치 폴더>\resources\engine"
   .\halo-engine.exe zwcad-convert "C:\path\to\sample1.dwg" "C:\path\to\out\sample1.dxf"
   .\halo-engine.exe zwcad-convert "C:\path\to\sample2.dwg" "C:\path\to\out\sample2.dxf"
   .\halo-engine.exe zwcad-convert "C:\path\to\sample3.dwg" "C:\path\to\out\sample3.dxf"
   .\halo-engine.exe zwcad-convert "C:\path\to\sample4.dwg" "C:\path\to\out\sample4.dxf"
   .\halo-engine.exe zwcad-convert "C:\path\to\sample5.dwg" "C:\path\to\out\sample5.dxf"
   ```

   `samples/`(읽기 전용 실도면 68장)에서 서로 다른 공종의 도면 5장을 고르면 좋다. 각 호출은
   종료 코드 0과 함께 JSON 한 줄을 stdout에 낸다(`{"converter": "zwcad-com", "zwcad_version":
   "...", "elapsed_s": ..., "warnings": [...], "output": "..."}`). 실패하면 종료 코드 1과
   `{"error": "..."}`.
4. 확인할 것:
   - ZWCAD 창이 화면에 보이지 않아야 한다(숨은 인스턴스).
   - 출력 DXF가 실제로 생성되고 0바이트가 아니어야 한다.
   - 5장 모두 성공하면 `zwcad_version` 값이 실제 설치된 ZWCAD 버전과 일치하는지 확인한다 —
     다르면 위 "SaveAs 버전 상수" 절이 아니라 `_read_version`/`Application.Version` 쪽 문제이니
     구분해서 기록한다.
   - `--dxf-version 2018` 등 다른 버전 인자로도 한 번 시도해 SaveAs 상수가 실제로 맞는지
     교차 확인한다(연 파일이 지정한 버전으로 저장됐는지는 ZWCAD의 "다른 이름으로 저장" 대화상자
     이력이나 DXF 헤더의 `$ACADVER`로 확인할 수 있다).
   - 일부러 매우 짧은 시간 제한(`--timeout 1`)으로 큰 도면 하나를 돌려 시간 초과 경로도 한 번
     확인한다: 작업 관리자에서 ZWCAD 프로세스가 실제로 정리되는지, 두 번째 호출이 다시 정상
     동작하는지(재시작 확인).
5. 결과를 `docs/gates/R1.md`의 `R1-GATE <항목>` 형식에 맞춰 기록한다(예:
   `R1-GATE zwcad-manual-check: PASS` 또는 실패 사유와 함께 `FAIL`). SaveAs 상수가 실제와
   다르면 `docs/gates/R1-questions.md` Q6에 실측값을 적고, 이 문서와
   `engine/src/halo_engine/compare/zwcad.py`의 `SAVE_AS_VERSIONS`를 실측값으로 고치는 후속
   태스크를 남긴다.

## 테스트 경계

- `engine/tests/compare/fake_com.py`의 `FakeComBackend`/`FakeApp`/`FakeDocument`가
  `ComBackend`(`create_app`, `kill_process_tree`)를 대신한다 — 실제 COM·레지스트리·Win32 API는
  전혀 건드리지 않는다. `sys.platform`을 `"win32"`로 몽키패치해 Windows 경로를 시뮬레이션한다.
  이 백엔드는 이후 태스크(마크업 DWG 저장 등, R1-09)가 그대로 재사용하도록 만들었다.
- `_find_registered_prog_id`(레지스트리 조회)와 `_pid_from_hwnd`(Win32 API 호출)는 COM 호출이
  아니라 각각 순수 레지스트리 읽기·Win32 API라서 `ComBackend`에 넣지 않고, 테스트에서 직접
  몽키패치한다(`engine/tests/compare/test_zwcad.py` 참고).
- `engine/tests/api/test_compare_zwcad.py`는 `GET /api/v1/compare/zwcad/status`가 200과
  `{available, installed, version, prog_id, reason}` 스키마를 낸다는 것, 그리고 다른 라우터와
  같은 베어러 인증을 요구한다는 것만 본다.
